"""
Recognition Stage
=================
Face recognition + identity management for tracked persons.
"""

import cv2
import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from core.pipeline.base import PipelineStage, FrameContext
from core.recognition.voting import IdentityVoter

logger = logging.getLogger("HumanAnalysis")


class RecognitionStage(PipelineStage):
    """Runs face recognition on tracked person ROIs in the background."""

    def __init__(self, face_recognizer, criminal_names: set,
                 rerecognize_every: int = 30, retry_base: float = 0.1, retry_max: float = 2.0,
                 voter: IdentityVoter = None, enabled: bool = True):
        super().__init__(name="recognition", enabled=enabled)
        self.face_recognizer = face_recognizer
        self.criminal_names = criminal_names
        self.rerecognize_every = rerecognize_every
        # Until a name is confirmed a track is retried every `retry_base` seconds (so the second vote
        # follows the first almost at once), backing off x2 per miss up to `retry_max` for people
        # whose face is never matched (backs, far away, not on the watchlist).
        self.retry_base = retry_base
        self.retry_max = retry_max
        self.voter = voter or IdentityVoter(window=5, min_votes=2)

        # Per-track state (persists across frames)
        self._id_name_map: dict = {}           # track_id → name
        self._id_conf: dict = {}               # track_id → latest real match confidence
        self._id_frame_count = defaultdict(int) # track_id → frames seen
        self._misses = defaultdict(int)         # track_id → consecutive attempts with no face match
        self._next_try: dict = {}               # track_id → monotonic time of the next attempt

        # Async state
        self._pending_tasks = set()
        # Threads only wait on the face worker processes (core/recognition/face_worker.py), which do
        # the real work in parallel; two keep one slow face from holding up the next person.
        self.executor = ThreadPoolExecutor(max_workers=2)

    def _run_recognition(self, track_id, proc_roi):
        try:
            # Key the recognizer's slow-detector cooldown per person: a faceless background track must
            # not use up the budget the real target needs.
            detail = self.face_recognizer.recognize_detail(proc_roi, source=(id(self), track_id))
            name = detail["name"] if detail else None
            self._misses[track_id] = 0 if detail else self._misses[track_id] + 1
            if detail:
                self._id_conf[track_id] = self.face_recognizer.confidence(
                    detail["distance"], self.face_recognizer.tolerance)
            self.voter.add(track_id, name)
            confirmed = self.voter.confirmed(track_id)
            if confirmed:
                if self._id_name_map.get(track_id) != confirmed and confirmed in self.criminal_names:
                    logger.info(f"WATCHLIST MATCH confirmed: {confirmed} | ID:{track_id}")
                self._id_name_map[track_id] = confirmed
            else:
                self._id_name_map[track_id] = "Unknown"      # votes decayed: never keep a stale name
        except Exception as e:
            logger.warning(f"Face recog failed ID {track_id}: {e}")
        finally:
            gap = min(self.retry_base * (2 ** min(self._misses[track_id], 8)), self.retry_max)
            self._next_try[track_id] = time.monotonic() + gap
            self._pending_tasks.discard(track_id)

    def process(self, ctx: FrameContext) -> FrameContext:
        fh, fw = ctx.frame.shape[:2]

        live = {t.track_id for t in ctx.tracks}
        self.voter.prune(live)
        for tid in [k for k in self._id_name_map if k not in live]:
            self._id_name_map.pop(tid, None)
            self._id_frame_count.pop(tid, None)
            self._id_conf.pop(tid, None)
            self._misses.pop(tid, None)
            self._next_try.pop(tid, None)

        now = time.monotonic()
        # Biggest (closest) people first: they are the ones whose faces can be read, and the face
        # jobs are queued in this order.
        by_size = sorted(ctx.tracks, key=lambda t: -((t.to_ltrb()[2] - t.to_ltrb()[0]) * (t.to_ltrb()[3] - t.to_ltrb()[1])))
        for track in by_size:
            if not track.is_confirmed():
                continue

            track_id = track.track_id
            # A lost track coasts on a predicted box over background: keep its name, but don't
            # spend face recognition (the slowest stage) on a crop with nobody in it.
            coasting = getattr(track, "time_since_update", 0) > 0
            x1, y1, x2, y2 = map(int, track.to_ltrb())
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(fw, x2), min(fh, y2)

            roi = ctx.frame[y1:y2, x1:x2]
            if roi.size == 0:
                continue

            # Decide whether to run face recognition
            if not coasting:
                self._id_frame_count[track_id] += 1
            n = self._id_frame_count[track_id]
            unconfirmed = self.voter.confirmed(track_id) is None
            should_recognize = (
                (track_id not in self._id_name_map
                 or n % self.rerecognize_every == 0
                 or (unconfirmed and now >= self._next_try.get(track_id, 0.0)))
                and track_id not in self._pending_tasks
                and not coasting
            )

            if should_recognize:
                # Faces are in the top of a full-body box; searching only that part makes the
                # upsampled HOG pass several times cheaper. A box cut off by the frame bottom is a
                # close-up whose face can sit lower, so it keeps the whole crop.
                if y2 < fh - 2 and roi.shape[0] > 2 * roi.shape[1]:
                    roi = roi[: max(1, int(roi.shape[0] * 0.45))]
                # Resize ROI if it's too large to prevent CPU bottleneck in HOG
                MAX_ROI_HEIGHT = 400
                h, w = roi.shape[:2]
                if h > MAX_ROI_HEIGHT:
                    scale = MAX_ROI_HEIGHT / h
                    proc_roi = cv2.resize(roi, (int(w * scale), MAX_ROI_HEIGHT))
                else:
                    proc_roi = roi.copy()

                self._pending_tasks.add(track_id)
                self.executor.submit(self._run_recognition, track_id, proc_roi)

            name = self._id_name_map.get(track_id, "Unknown")
            ctx.identities[track_id] = name
            if name in self._id_conf or track_id in self._id_conf:
                ctx.identity_conf[track_id] = self._id_conf.get(track_id, 0.0)

            if name in self.criminal_names:
                ctx.criminal_ids.add(track_id)
                if name not in ctx.active_criminals:
                    ctx.active_criminals.append(name)

        return ctx
