import unittest
import uuid
from unittest.mock import patch

from fastapi import HTTPException, Request

from app.main import ContractTypeVoteRequest, vote_contract_type


class FakeVotesQuery:
    def __init__(self, votes):
        self.votes = votes

    def group_by(self, _column):
        return self

    def all(self):
        counts = {}
        for vote in self.votes.values():
            counts[vote.choice] = counts.get(vote.choice, 0) + 1
        return list(counts.items())


class FakeVotesDb:
    def __init__(self):
        self.votes = {}

    def get(self, _model, voter_hash):
        return self.votes.get(voter_hash)

    def add(self, vote):
        self.votes[vote.voter_hash] = vote

    def commit(self):
        pass

    def query(self, *_columns):
        return FakeVotesQuery(self.votes)


class ContractTypePollTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeVotesDb()
        self.request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1234)})
        self.voter_id = uuid.uuid4()

    def vote(self, choice, other_text=""):
        payload = ContractTypeVoteRequest(voter_id=self.voter_id, choice=choice, other_text=other_text)
        with patch("app.main.check_daily_rate_limit"):
            return vote_contract_type(payload, self.request, self.db)

    def test_vote_can_be_changed_without_increasing_total(self):
        first = self.vote("ai_saas")
        self.assertEqual(first["total"], 1)

        second = self.vote("universal")
        self.assertEqual(second["total"], 1)
        counts = {option["id"]: option["votes"] for option in second["options"]}
        self.assertEqual(counts["ai_saas"], 0)
        self.assertEqual(counts["universal"], 1)

    def test_other_requires_a_contract_type(self):
        with self.assertRaises(HTTPException) as error:
            self.vote("other")
        self.assertEqual(error.exception.status_code, 400)

    def test_rejects_unknown_choice(self):
        with self.assertRaises(HTTPException) as error:
            self.vote("unknown")
        self.assertEqual(error.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
