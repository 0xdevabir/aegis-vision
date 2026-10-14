"""Build models/action_stgcn_ntu60.onnx from MMAction2's pretrained ST-GCN (Apache-2.0).

The checkpoint is `stgcn_8xb16-joint-u100-80e_ntu60-xsub-keypoint-2d` (NTU RGB+D 60, 2D COCO-17
keypoints, 88.95% top-1). ST-GCN is small, so it is rebuilt here in plain PyTorch with the same
parameter names: no mmcv / mmengine / mmaction install. The graph convolution is written as one
matmul against a constant matrix so OpenCV's DNN module can run the exported file.

    python scripts/export_action_model.py            # writes models/action_stgcn_ntu60.onnx
"""

import hashlib
import sys
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.analysis.action import ACTION_MODEL, CLIP_LEN, NUM_JOINTS, NUM_PERSON  # noqa: E402

CKPT_URL = ("https://download.openmmlab.com/mmaction/v1.0/skeleton/stgcn/"
            "stgcn_8xb16-joint-u100-80e_ntu60-xsub-keypoint-2d/"
            "stgcn_8xb16-joint-u100-80e_ntu60-xsub-keypoint-2d_20221129-484a394a.pth")
CKPT_SHA256_PREFIX = "484a394a"      # OpenMMLab names files after the hash

# COCO-17 skeleton, as mmaction.models.utils.Graph(layout='coco', mode='stgcn_spatial')
COCO_INWARD = [(15, 13), (13, 11), (16, 14), (14, 12), (11, 5), (12, 6), (9, 7), (7, 5),
               (10, 8), (8, 6), (5, 0), (6, 0), (1, 0), (3, 1), (2, 0), (4, 2)]
CENTER = 0


def stgcn_spatial_adjacency() -> np.ndarray:
    n = NUM_JOINTS
    link = np.eye(n)
    for i, j in COCO_INWARD:
        link[i, j] = link[j, i] = 1
    hop = np.full((n, n), np.inf)
    hop[link > 0] = 1
    hop[np.eye(n) > 0] = 0
    adj = (hop <= 1).astype(float)
    deg = adj.sum(0)
    norm = adj / deg[None, :]                     # every joint has a self-loop, so deg > 0
    a = [np.zeros((n, n)) for _ in range(3)]      # self, closer to centre, further from centre
    for i in range(n):
        for j in range(n):
            if hop[j, i] == 0:
                a[0][j, i] = norm[j, i]
            elif hop[j, i] == 1:
                (a[1] if hop[j, CENTER] >= hop[i, CENTER] else a[2])[j, i] = norm[j, i]
    return np.stack(a).astype(np.float32)


class UnitGCN(nn.Module):
    def __init__(self, cin, cout, A):
        super().__init__()
        self.k = A.shape[0]
        self.register_buffer("A", A)
        self.PA = nn.Parameter(torch.ones_like(A))          # adaptive='importance'
        self.conv = nn.Conv2d(cin, cout * self.k, 1)
        self.bn = nn.BatchNorm2d(cout)
        self.act = nn.ReLU()

    def forward(self, x):
        n, _, t, v = x.shape
        x = self.conv(x).view(n, self.k, -1, t, v)
        c = x.shape[2]
        # einsum('nkctv,kvw->nctw') as a single matmul with a constant (k*v, w) matrix
        x = x.permute(0, 2, 3, 1, 4).reshape(n, c * t, self.k * v)
        x = torch.matmul(x, (self.A * self.PA).reshape(self.k * v, v)).view(n, c, t, v)
        return self.act(self.bn(x))


class UnitTCN(nn.Module):
    def __init__(self, cin, cout, kernel_size=9, stride=1):
        super().__init__()
        self.conv = nn.Conv2d(cin, cout, (kernel_size, 1), padding=((kernel_size - 1) // 2, 0),
                              stride=(stride, 1))
        self.bn = nn.BatchNorm2d(cout)

    def forward(self, x):
        return self.bn(self.conv(x))


class Block(nn.Module):
    def __init__(self, cin, cout, A, stride=1, residual=True):
        super().__init__()
        self.gcn = UnitGCN(cin, cout, A)
        self.tcn = UnitTCN(cout, cout, 9, stride)
        self.relu = nn.ReLU()
        if not residual:
            self.residual = None
        elif cin == cout and stride == 1:
            self.residual = nn.Identity()
        else:
            self.residual = UnitTCN(cin, cout, 1, stride)

    def forward(self, x):
        res = 0 if self.residual is None else self.residual(x)
        return self.relu(self.tcn(self.gcn(x)) + res)


class STGCN(nn.Module):
    """Backbone + GCNHead of mmaction2's RecognizerGCN; input (N, M, T, V, C) → class logits."""

    def __init__(self, num_classes=60):
        super().__init__()
        A = torch.from_numpy(stgcn_spatial_adjacency())
        self.data_bn = nn.BatchNorm1d(3 * NUM_JOINTS)
        blocks = [Block(3, 64, A.clone(), residual=False)]
        cin = 64
        for i in range(2, 11):                       # inflate + downsample at stages 5 and 8
            cout = cin * 2 if i in (5, 8) else cin
            blocks.append(Block(cin, cout, A.clone(), 2 if i in (5, 8) else 1))
            cin = cout
        self.gcn = nn.ModuleList(blocks)
        self.fc = nn.Linear(256, num_classes)

    def forward(self, x):
        n, m, t, v, c = x.shape
        x = x.permute(0, 1, 3, 4, 2).reshape(n * m, v * c, t)
        x = self.data_bn(x).view(n, m, v, c, t).permute(0, 1, 3, 4, 2).reshape(n * m, c, t, v)
        for block in self.gcn:
            x = block(x)
        x = x.mean(dim=(2, 3)).view(n, m, -1).mean(dim=1)
        return self.fc(x)


def load_checkpoint(model: STGCN, path: Path) -> None:
    state = torch.load(path, map_location="cpu", weights_only=False)
    state = state.get("state_dict", state)
    renamed = {}
    for k, v in state.items():
        if k.startswith("backbone."):
            renamed[k[len("backbone."):]] = v
        elif k.startswith("cls_head.fc."):
            renamed[k[len("cls_head."):]] = v
    missing, unexpected = model.load_state_dict(renamed, strict=False)
    missing = [k for k in missing if not k.endswith(".A")]     # adjacency is rebuilt, not loaded
    if missing or unexpected:
        raise RuntimeError(f"checkpoint mismatch: missing={missing} unexpected={unexpected}")
    for k in [k for k in renamed if k.endswith(".A")]:         # the graph must match exactly
        if not torch.allclose(renamed[k], dict(model.named_buffers())[k], atol=1e-6):
            raise RuntimeError(f"adjacency {k} differs from the checkpoint")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        ckpt = Path(tmp) / "stgcn.pth"
        print("Downloading ST-GCN checkpoint (12 MB) from download.openmmlab.com…")
        urllib.request.urlretrieve(CKPT_URL, ckpt)
        digest = hashlib.sha256(ckpt.read_bytes()).hexdigest()
        if not digest.startswith(CKPT_SHA256_PREFIX):
            raise RuntimeError(f"checkpoint hash {digest[:8]} != {CKPT_SHA256_PREFIX}")
        model = STGCN()
        load_checkpoint(model, ckpt)
    model.eval()

    dummy = torch.randn(1, NUM_PERSON, CLIP_LEN, NUM_JOINTS, 3)
    ACTION_MODEL.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(model, dummy, str(ACTION_MODEL), input_names=["skeleton"],
                      output_names=["logits"], opset_version=13, dynamo=False)

    import cv2
    net = cv2.dnn.readNetFromONNX(str(ACTION_MODEL))
    net.setInput(dummy.numpy())
    diff = float(np.abs(net.forward() - model(dummy).detach().numpy()).max())
    if diff > 1e-3:
        raise RuntimeError(f"OpenCV output differs from PyTorch by {diff}")
    print(f"Wrote {ACTION_MODEL.relative_to(ROOT)} (OpenCV vs PyTorch max diff {diff:.1e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
