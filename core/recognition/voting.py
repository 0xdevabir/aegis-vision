"""Multi-frame identity voting: one face match is never enough to name a track."""

from collections import Counter, defaultdict, deque
from typing import Optional


class IdentityVoter:
    """Sliding window of reads per track; a miss (None) is a vote against any name."""

    def __init__(self, window: int = 5, min_votes: int = 2):
        self.window = window
        self.min_votes = min_votes
        self._votes = defaultdict(lambda: deque(maxlen=window))

    def add(self, track_id: int, name: Optional[str]) -> None:
        """Record a read: the matched name, or None for a miss/ambiguous read."""
        self._votes[track_id].append(name)

    def confirmed(self, track_id: int) -> Optional[str]:
        votes = [v for v in self._votes.get(track_id, ()) if v]
        if not votes:
            return None
        name, n = Counter(votes).most_common(1)[0]
        return name if n >= self.min_votes else None

    def prune(self, live_ids) -> None:
        for tid in [t for t in self._votes if t not in live_ids]:
            del self._votes[tid]
