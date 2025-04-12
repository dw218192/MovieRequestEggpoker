from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from dataclasses_json import DataClassJsonMixin
from typing import Literal
from datetime import datetime
from asyncio import Lock
import pathlib
import logging
import sys
import os
import json
import app.qbittorrent as qbittorrent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class User(DataClassJsonMixin):
    id: str
    username: str


@dataclass(frozen=True)
class Torrent(DataClassJsonMixin):
    infohash: str


@dataclass
class MovieRequest(DataClassJsonMixin):
    torrent: Torrent
    created_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    ref_count: int = 1

    def __hash__(self) -> int:
        return hash(self.torrent)

    def __eq__(self, value: object) -> bool:
        if isinstance(value, MovieRequest):
            return self.torrent == value.torrent
        elif isinstance(value, Torrent):
            return self.torrent == value
        elif isinstance(value, str):
            return self.torrent.infohash == value
        return False


class IDatabase(ABC):
    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def close(self): ...

    @abstractmethod
    async def has_request(self, user: User, torrent: Torrent) -> bool: ...

    @abstractmethod
    async def make_request(self, user: User, torrent: Torrent) -> MovieRequest: ...

    @abstractmethod
    async def get_requests(self, user: User) -> list[MovieRequest]: ...

    @abstractmethod
    async def cancel_request(self, user: User, torrent: Torrent) -> bool: ...

    @abstractmethod
    def drop(self): ...


@dataclass
class JsonDB:
    version: Literal[0]
    all_requests: list[MovieRequest]
    user_to_torrents: dict[User, list[Torrent]]

    def to_json(self) -> str:
        dct = {}
        dct["version"] = self.version
        dct["all_requests"] = [req.to_dict() for req in self.all_requests]
        dct["user_to_torrents"] = []
        for user, torrents in self.user_to_torrents.items():
            dct["user_to_torrents"].append(
                {
                    "user": user.to_dict(),
                    "torrents": [torrent.to_dict() for torrent in torrents],
                }
            )
        return json.dumps(dct)

    @staticmethod
    def from_json(json_str: str) -> "JsonDB":
        dct = json.loads(json_str)
        all_requests = [MovieRequest.from_dict(req) for req in dct["all_requests"]]
        user_to_torrents = {}
        for user_dict in dct["user_to_torrents"]:
            user = User.from_dict(user_dict["user"])
            torrents = [Torrent.from_dict(torrent) for torrent in user_dict["torrents"]]
            user_to_torrents[user] = torrents
        return JsonDB(
            version=dct["version"],
            all_requests=all_requests,
            user_to_torrents=user_to_torrents,
        )


class JsonDatabase(IDatabase):
    SUPPORTED_VERSION = 0

    def __init__(self, db_path: str):
        self.db_path = pathlib.Path(db_path)
        self.lock = Lock()

        if self.db_path.exists():
            self._db = JsonDB.from_json(self.db_path.read_text())
        else:
            self._db = JsonDB(
                version=self.SUPPORTED_VERSION,
                all_requests=[],
                user_to_torrents={},
            )

        self.__assert(
            self.SUPPORTED_VERSION >= self._db.version,
            f"Unsupported database version {self._db.version}, expected {self.SUPPORTED_VERSION}.",
        )

    def __save(self):
        if not self.db_path.exists():
            pathlib.Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db_path.write_text(self._db.to_json())

    def __assert(self, cond, msg: str):
        if not cond:
            logger.fatal(f"invariant violation: {msg}")
            sys.exit(1)

    def __get_or_create_request(self, torrent: Torrent) -> tuple[MovieRequest, bool]:
        """
        Get the request if it exists, otherwise create a new one.
        The boolean indicates whether the request was newly created or not.
        """
        all_reqs = self._db.all_requests
        for req in all_reqs:
            if req.torrent == torrent:
                return req, False
        return MovieRequest(torrent), True

    def connect(self):
        self.__save()

    def close(self):
        self.__save()

    async def has_request(self, user: User, torrent: Torrent) -> bool:
        user_to_torrents = self._db.user_to_torrents
        if user not in user_to_torrents:
            return False
        torrents = user_to_torrents[user]
        if torrent not in torrents:
            return False

        return True

    async def make_request(self, user: User, torrent: Torrent) -> MovieRequest:
        async with self.lock:
            user_to_torrents = self._db.user_to_torrents
            if user not in user_to_torrents:
                user_to_torrents[user] = []

            req, is_new = self.__get_or_create_request(torrent)

            if torrent in user_to_torrents[user]:
                logger.warning(
                    f"User {user.username} already has a request for torrent {torrent.infohash}."
                )
                self.__assert(
                    not is_new, "torrent is new but already in user_to_torrents"
                )
                return req
            else:
                user_to_torrents[user].append(torrent)

            if is_new:
                self._db.all_requests.append(req)
            else:
                req.ref_count += 1

            logger.info(
                f"User {user.username} made a request for torrent {torrent.infohash}."
            )
            self.__save()
            return req

    async def get_requests(self, user: User) -> list[MovieRequest]:
        user_to_torrents = self._db.user_to_torrents
        if user not in user_to_torrents:
            return []
        torrents = user_to_torrents[user]

        ret = []
        for torrent in torrents:
            req, is_new = self.__get_or_create_request(torrent)
            self.__assert(not is_new, "torrent is new but already in user_to_torrents")

            ret.append(req)
        return ret

    async def cancel_request(self, user: User, torrent: Torrent) -> bool:
        async with self.lock:
            user_to_torrents = self._db.user_to_torrents
            if user not in user_to_torrents:
                logger.warning(f"User {user.username} does not have any requests.")
                return False
            torrents = user_to_torrents[user]
            if torrent not in torrents:
                logger.warning(
                    f"User {user.username} does not have a request for torrent {torrent.infohash}."
                )
                return False
            torrents.remove(torrent)

            req, is_new = self.__get_or_create_request(torrent)
            self.__assert(not is_new, "torrent is new but already in user_to_torrents")

            req.ref_count -= 1
            self.__assert(req.ref_count >= 0, "ref_count < 0")

            if req.ref_count == 0:
                self._db.all_requests.remove(req)
                await qbittorrent.delete_torrent(
                    torrent_hashes=torrent.infohash, delete_files=True
                )

            self.__save()
            return True

    def drop(self):
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass

        self._db = JsonDB(
            version=self.SUPPORTED_VERSION,
            all_requests=[],
            user_to_torrents={},
        )
