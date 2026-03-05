"""Data models for Loomio API responses."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


class PollType(Enum):
    """Types of polls supported by Loomio."""

    PROPOSAL = "proposal"
    POLL = "poll"
    COUNT = "count"
    SCORE = "score"
    RANKED_CHOICE = "ranked_choice"
    MEETING = "meeting"
    DOT_VOTE = "dot_vote"


@dataclass
class User:
    """Loomio user."""

    id: int
    name: str
    username: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None


@dataclass
class Group:
    """Loomio group."""

    id: int
    name: str
    description: Optional[str] = None
    members_count: int = 0
    parent_id: Optional[int] = None


@dataclass
class PollOption:
    """A single option in a poll."""

    name: str
    score: float = 0
    voter_count: int = 0


@dataclass
class Poll:
    """Loomio poll."""

    id: int
    title: str
    poll_type: str
    details: Optional[str] = None
    closing_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    anonymous: bool = False
    voters_count: int = 0
    undecided_voters_count: int = 0
    options: List[PollOption] = field(default_factory=list)
    author_id: Optional[int] = None
    group_id: Optional[int] = None
    discussion_id: Optional[int] = None
    outcome: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None

    @property
    def is_proposal(self) -> bool:
        return self.poll_type == PollType.PROPOSAL.value


@dataclass
class VoteRecord:
    """A single vote (stance) on a poll."""

    id: int
    poll_id: int
    participant_id: int
    choice: Optional[str] = None
    reason: Optional[str] = None
    score: Optional[float] = None
    rankings: Optional[Dict[str, int]] = None
    created_at: Optional[datetime] = None
    participant_name: Optional[str] = None


@dataclass
class Comment:
    """A comment on a poll or discussion."""

    id: int
    body: str
    author_id: int
    author_name: Optional[str] = None
    created_at: Optional[datetime] = None
    poll_id: Optional[int] = None
    discussion_id: Optional[int] = None


@dataclass
class Task:
    """A task in a Loomio group."""

    id: int
    name: str
    done: bool = False
    author_id: Optional[int] = None
    due_on: Optional[datetime] = None
    assignee_ids: List[int] = field(default_factory=list)
    group_id: Optional[int] = None
