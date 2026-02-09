"""Loomio API client."""

import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

import requests

from signalinator_core import get_logger

from .models import Poll, PollOption, PollType, User, Group, VoteRecord, Comment, Task

logger = get_logger(__name__)


class LoomioClientError(Exception):
    """Exception raised for Loomio API errors."""

    pass


class LoomioClient:
    """Client for Loomio API."""

    DEFAULT_URL = "http://localhost:3000"

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or os.getenv("LOOMIO_API_KEY")
        self.base_url = (base_url or os.getenv("LOOMIO_URL", self.DEFAULT_URL)).rstrip("/")

        if not self.api_key:
            raise LoomioClientError("LOOMIO_API_KEY environment variable is required")

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Dict = None,
        json_data: Dict = None,
    ) -> Dict:
        """Make an API request."""
        url = f"{self.base_url}/api/v1/{endpoint.lstrip('/')}"

        # Add API key to params
        params = params or {}
        params["api_key"] = self.api_key

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=30,
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP {e.response.status_code}"
            try:
                error_data = e.response.json()
                error_msg = error_data.get("error", error_msg)
            except Exception:
                pass
            raise LoomioClientError(f"Loomio API error: {error_msg}")
        except requests.exceptions.RequestException as e:
            raise LoomioClientError(f"Network error: {e}")

    def _get(self, endpoint: str, params: Dict = None) -> Dict:
        return self._request("GET", endpoint, params=params)

    def _post(self, endpoint: str, data: Dict = None, params: Dict = None) -> Dict:
        return self._request("POST", endpoint, params=params, json_data=data)

    def _patch(self, endpoint: str, data: Dict = None, params: Dict = None) -> Dict:
        return self._request("PATCH", endpoint, params=params, json_data=data)

    def _delete(self, endpoint: str, params: Dict = None) -> Dict:
        return self._request("DELETE", endpoint, params=params)

    def _parse_datetime(self, value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    # ==================== Users ====================

    def create_user(self, name: str, email: str) -> User:
        """Create a new Loomio user."""
        data = self._post("users", {"name": name, "email": email})
        user_data = data.get("users", [{}])[0] if "users" in data else data
        return User(
            id=user_data["id"],
            name=user_data.get("name", name),
            username=user_data.get("username"),
            email=email,
        )

    def lookup_user(self, username: str) -> Optional[User]:
        """Look up a user by username."""
        try:
            data = self._get(f"users/username/{username}")
            user_data = data.get("users", [{}])[0] if "users" in data else data
            return User(
                id=user_data["id"],
                name=user_data.get("name", ""),
                username=user_data.get("username"),
            )
        except LoomioClientError:
            return None

    def update_user_name(self, username: str, new_name: str) -> bool:
        """Update a user's display name."""
        user = self.lookup_user(username)
        if not user:
            return False
        self._patch(f"users/{user.id}", {"name": new_name})
        return True

    # ==================== Groups ====================

    def create_group(
        self,
        name: str,
        description: str = None,
        parent_id: int = None,
    ) -> Group:
        """Create a new Loomio group."""
        data = {"name": name}
        if description:
            data["description"] = description
        if parent_id:
            data["parent_id"] = parent_id

        result = self._post("groups", data)
        group_data = result.get("groups", [{}])[0] if "groups" in result else result
        return Group(
            id=group_data["id"],
            name=group_data.get("name", name),
            description=group_data.get("description"),
        )

    def get_group(self, group_id: int) -> Optional[Group]:
        """Get a group by ID."""
        try:
            data = self._get(f"groups/{group_id}")
            group_data = data.get("groups", [{}])[0] if "groups" in data else data
            return Group(
                id=group_data["id"],
                name=group_data.get("name", ""),
                description=group_data.get("description"),
                members_count=group_data.get("members_count", 0),
            )
        except LoomioClientError:
            return None

    def get_group_members(self, group_id: int) -> List[User]:
        """Get members of a group."""
        data = self._get(f"groups/{group_id}/memberships")
        users = []
        for user_data in data.get("users", []):
            users.append(User(
                id=user_data["id"],
                name=user_data.get("name", ""),
                username=user_data.get("username"),
            ))
        return users

    def add_member_to_group(self, group_id: int, user_id: int) -> bool:
        """Add a user to a group."""
        try:
            self._post(f"memberships", {"group_id": group_id, "user_id": user_id})
            return True
        except LoomioClientError:
            return False

    def invite_to_group(self, group_id: int, emails: List[str]) -> bool:
        """Invite users to a group by email."""
        try:
            self._post(f"groups/{group_id}/invitations", {"emails": emails})
            return True
        except LoomioClientError:
            return False

    # ==================== Polls ====================

    def _parse_poll(self, poll_data: Dict, users: Dict[int, str] = None) -> Poll:
        """Parse poll data into a Poll object."""
        users = users or {}

        options = []
        for opt in poll_data.get("poll_options", []):
            options.append(PollOption(
                name=opt.get("name", ""),
                score=opt.get("score", 0),
                voter_count=opt.get("voter_count", 0),
            ))

        return Poll(
            id=poll_data["id"],
            title=poll_data.get("title", ""),
            poll_type=poll_data.get("poll_type", "poll"),
            details=poll_data.get("details"),
            closing_at=self._parse_datetime(poll_data.get("closing_at")),
            closed_at=self._parse_datetime(poll_data.get("closed_at")),
            anonymous=poll_data.get("anonymous", False),
            voters_count=poll_data.get("voters_count", 0),
            undecided_voters_count=poll_data.get("undecided_voters_count", 0),
            options=options,
            author_id=poll_data.get("author_id"),
            group_id=poll_data.get("group_id"),
            discussion_id=poll_data.get("discussion_id"),
            outcome=poll_data.get("outcome"),
            raw_data=poll_data,
        )

    def create_poll(
        self,
        title: str,
        poll_type: PollType,
        group_id: int,
        details: str = None,
        options: List[str] = None,
        closing_hours: int = 72,
        closing_at: datetime = None,
        anonymous: bool = False,
        author_id: int = None,
    ) -> Poll:
        """Create a new poll."""
        data = {
            "title": title,
            "poll_type": poll_type.value,
            "group_id": group_id,
            "anonymous": anonymous,
        }

        if details:
            data["details"] = details

        if options:
            data["poll_option_names"] = options
        elif poll_type == PollType.PROPOSAL:
            data["poll_option_names"] = ["agree", "disagree", "abstain", "block"]

        if closing_at:
            data["closing_at"] = closing_at.isoformat()
        else:
            data["closing_at"] = (datetime.now(timezone.utc) + timedelta(hours=closing_hours)).isoformat()

        if author_id:
            data["author_id"] = author_id

        result = self._post("polls", data)
        poll_data = result.get("polls", [{}])[0] if "polls" in result else result
        return self._parse_poll(poll_data)

    def get_poll(self, poll_id: int) -> Optional[Poll]:
        """Get a poll by ID."""
        try:
            data = self._get(f"polls/{poll_id}")
            poll_data = data.get("polls", [{}])[0] if "polls" in data else data
            return self._parse_poll(poll_data)
        except LoomioClientError:
            return None

    def list_polls(
        self,
        group_id: int,
        status: str = "active",
    ) -> List[Poll]:
        """List polls for a group."""
        params = {"group_id": group_id}
        if status == "active":
            params["status"] = "active"
        elif status == "closed":
            params["status"] = "closed"

        data = self._get("polls", params=params)
        polls = []
        for poll_data in data.get("polls", []):
            polls.append(self._parse_poll(poll_data))
        return polls

    def close_poll(self, poll_id: int) -> bool:
        """Close a poll early."""
        try:
            self._post(f"polls/{poll_id}/close")
            return True
        except LoomioClientError:
            return False

    def reopen_poll(self, poll_id: int, closing_hours: int = 24) -> bool:
        """Reopen a closed poll."""
        closing_at = (datetime.now(timezone.utc) + timedelta(hours=closing_hours)).isoformat()
        try:
            self._post(f"polls/{poll_id}/reopen", {"closing_at": closing_at})
            return True
        except LoomioClientError:
            return False

    def extend_poll(self, poll_id: int, additional_hours: int) -> bool:
        """Extend a poll's deadline."""
        poll = self.get_poll(poll_id)
        if not poll or not poll.closing_at:
            return False

        new_closing = poll.closing_at + timedelta(hours=additional_hours)
        try:
            self._patch(f"polls/{poll_id}", {"closing_at": new_closing.isoformat()})
            return True
        except LoomioClientError:
            return False

    def set_outcome(self, poll_id: int, outcome: str) -> bool:
        """Set the outcome text for a poll."""
        try:
            self._post(f"outcomes", {"poll_id": poll_id, "statement": outcome})
            return True
        except LoomioClientError:
            return False

    def get_non_voters(self, poll_id: int) -> List[User]:
        """Get users who haven't voted on a poll."""
        try:
            data = self._get(f"polls/{poll_id}/non_voters")
            users = []
            for user_data in data.get("users", []):
                users.append(User(
                    id=user_data["id"],
                    name=user_data.get("name", ""),
                    username=user_data.get("username"),
                ))
            return users
        except LoomioClientError:
            return []

    # ==================== Stances (Votes) ====================

    def cast_vote(
        self,
        poll_id: int,
        choice: str,
        user_id: int,
        reason: str = None,
    ) -> VoteRecord:
        """Cast a vote on a poll."""
        data = {
            "poll_id": poll_id,
            "stance_choices_attributes": [{"poll_option_id": choice}],
            "participant_id": user_id,
        }
        if reason:
            data["reason"] = reason

        result = self._post("stances", data)
        stance_data = result.get("stances", [{}])[0] if "stances" in result else result
        return VoteRecord(
            id=stance_data.get("id", 0),
            poll_id=poll_id,
            participant_id=user_id,
            choice=choice,
            reason=reason,
        )

    def cast_ranked_vote(
        self,
        poll_id: int,
        rankings: Dict[str, int],
        user_id: int,
        reason: str = None,
    ) -> VoteRecord:
        """Cast a ranked choice vote."""
        choices = [
            {"poll_option_id": opt, "score": rank}
            for opt, rank in rankings.items()
        ]
        data = {
            "poll_id": poll_id,
            "stance_choices_attributes": choices,
            "participant_id": user_id,
        }
        if reason:
            data["reason"] = reason

        result = self._post("stances", data)
        stance_data = result.get("stances", [{}])[0] if "stances" in result else result
        return VoteRecord(
            id=stance_data.get("id", 0),
            poll_id=poll_id,
            participant_id=user_id,
            rankings=rankings,
            reason=reason,
        )

    def cast_meeting_vote(
        self,
        poll_id: int,
        available_times: List[str],
        user_id: int,
        reason: str = None,
    ) -> VoteRecord:
        """Cast a meeting poll vote."""
        choices = [{"poll_option_id": t, "score": 1} for t in available_times]
        data = {
            "poll_id": poll_id,
            "stance_choices_attributes": choices,
            "participant_id": user_id,
        }
        if reason:
            data["reason"] = reason

        result = self._post("stances", data)
        stance_data = result.get("stances", [{}])[0] if "stances" in result else result
        return VoteRecord(
            id=stance_data.get("id", 0),
            poll_id=poll_id,
            participant_id=user_id,
            reason=reason,
        )

    def remove_vote(self, stance_id: int, participant_id: int) -> bool:
        """Remove a vote."""
        try:
            self._delete(f"stances/{stance_id}", params={"participant_id": participant_id})
            return True
        except LoomioClientError:
            return False

    def get_stances(self, poll_id: int) -> List[VoteRecord]:
        """Get all votes for a poll."""
        data = self._get(f"polls/{poll_id}/stances")
        votes = []
        users = {u["id"]: u.get("name", "") for u in data.get("users", [])}

        for stance in data.get("stances", []):
            participant_id = stance.get("participant_id")
            votes.append(VoteRecord(
                id=stance["id"],
                poll_id=poll_id,
                participant_id=participant_id,
                choice=stance.get("poll_option_id"),
                reason=stance.get("reason"),
                score=stance.get("score"),
                created_at=self._parse_datetime(stance.get("created_at")),
                participant_name=users.get(participant_id),
            ))
        return votes

    # ==================== Comments ====================

    def add_comment(
        self,
        body: str,
        user_id: int,
        poll_id: int = None,
        discussion_id: int = None,
    ) -> Comment:
        """Add a comment to a poll or discussion."""
        data = {"body": body, "author_id": user_id}
        if poll_id:
            data["poll_id"] = poll_id
        if discussion_id:
            data["discussion_id"] = discussion_id

        result = self._post("comments", data)
        comment_data = result.get("comments", [{}])[0] if "comments" in result else result
        return Comment(
            id=comment_data.get("id", 0),
            body=body,
            author_id=user_id,
            poll_id=poll_id,
            discussion_id=discussion_id,
        )

    def get_comments(
        self,
        poll_id: int = None,
        discussion_id: int = None,
        limit: int = 10,
    ) -> List[Comment]:
        """Get comments for a poll or discussion."""
        params = {"per_page": limit}
        if poll_id:
            params["poll_id"] = poll_id
        if discussion_id:
            params["discussion_id"] = discussion_id

        data = self._get("comments", params=params)
        users = {u["id"]: u.get("name", "") for u in data.get("users", [])}

        comments = []
        for c in data.get("comments", []):
            author_id = c.get("author_id")
            comments.append(Comment(
                id=c["id"],
                body=c.get("body", ""),
                author_id=author_id,
                author_name=users.get(author_id),
                created_at=self._parse_datetime(c.get("created_at")),
                poll_id=c.get("poll_id"),
                discussion_id=c.get("discussion_id"),
            ))
        return comments

    # ==================== Tasks ====================

    def get_group_tasks(self, group_id: int, done: bool = None) -> List[Task]:
        """Get tasks for a group."""
        params = {"group_id": group_id}
        if done is not None:
            params["done"] = done

        data = self._get("tasks", params=params)
        tasks = []
        for t in data.get("tasks", []):
            tasks.append(Task(
                id=t["id"],
                name=t.get("name", ""),
                done=t.get("done", False),
                author_id=t.get("author_id"),
                due_on=self._parse_datetime(t.get("due_on")),
                assignee_ids=t.get("assignee_ids", []),
                group_id=group_id,
            ))
        return tasks

    def create_task(
        self,
        group_id: int,
        name: str,
        author_id: int,
        due_on: datetime = None,
        assignee_ids: List[int] = None,
    ) -> Task:
        """Create a new task."""
        data = {
            "group_id": group_id,
            "name": name,
            "author_id": author_id,
        }
        if due_on:
            data["due_on"] = due_on.isoformat()
        if assignee_ids:
            data["assignee_ids"] = assignee_ids

        result = self._post("tasks", data)
        task_data = result.get("tasks", [{}])[0] if "tasks" in result else result
        return Task(
            id=task_data.get("id", 0),
            name=name,
            author_id=author_id,
            group_id=group_id,
            due_on=due_on,
            assignee_ids=assignee_ids or [],
        )

    def update_task(
        self,
        task_id: int,
        done: bool = None,
        due_on: datetime = None,
        actor_id: int = None,
    ) -> bool:
        """Update a task."""
        data = {}
        if done is not None:
            data["done"] = done
        if due_on:
            data["due_on"] = due_on.isoformat()
        if actor_id:
            data["actor_id"] = actor_id

        try:
            self._patch(f"tasks/{task_id}", data)
            return True
        except LoomioClientError:
            return False

    def delete_task(self, task_id: int) -> bool:
        """Delete a task."""
        try:
            self._delete(f"tasks/{task_id}")
            return True
        except LoomioClientError:
            return False
