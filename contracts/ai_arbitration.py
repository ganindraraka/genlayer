# ai_arbitration.py
# GenLayer Intelligent Contract: AI Arbitration System
# 
# Dua pihak submit kasus sengketa mereka, AI (LLM) memutuskan siapa yang menang
# berdasarkan argumen, bukti, dan referensi web yang diambil secara on-chain.

from genlayer import *
from genlayer.py.storage import DynArray, TreeMap
import json


@gl.contract
class AIArbitration:
    """
    AI-powered dispute resolution contract.
    Two parties submit their case arguments.
    LLM evaluates both sides and issues a verdict with reasoning.
    """

    # --- Storage ---
    dispute_id_counter: u256
    disputes: TreeMap[u256, Dispute]
    user_disputes: TreeMap[Address, DynArray[u256]]

    def __init__(self) -> None:
        self.dispute_id_counter = u256(0)

    # --- Read Methods ---

    @gl.public.view
    def get_dispute(self, dispute_id: u256) -> dict:
        """Get full dispute details."""
        if dispute_id not in self.disputes:
            raise Exception(f"Dispute #{dispute_id} not found")
        d = self.disputes[dispute_id]
        return {
            "id": int(dispute_id),
            "claimant": str(d.claimant),
            "respondent": str(d.respondent),
            "title": d.title,
            "claimant_argument": d.claimant_argument,
            "respondent_argument": d.respondent_argument,
            "respondent_responded": d.respondent_responded,
            "verdict": d.verdict,
            "winner": str(d.winner),
            "reasoning": d.reasoning,
            "status": d.status,
        }

    @gl.public.view
    def get_dispute_count(self) -> int:
        return int(self.dispute_id_counter)

    @gl.public.view
    def get_user_disputes(self, user: Address) -> list:
        if user not in self.user_disputes:
            return []
        return [int(did) for did in self.user_disputes[user]]

    # --- Write Methods ---

    @gl.public.write
    def open_dispute(
        self,
        respondent: Address,
        title: str,
        argument: str,
        evidence_url: str = "",
    ) -> u256:
        """
        Claimant opens a new dispute against respondent.
        Optionally provide a URL as external evidence.
        """
        assert len(title) > 0, "Title cannot be empty"
        assert len(argument) >= 20, "Argument must be at least 20 characters"
        assert respondent != gl.message.sender, "Cannot dispute yourself"

        dispute_id = self.dispute_id_counter
        self.dispute_id_counter = u256(int(self.dispute_id_counter) + 1)

        d = Dispute()
        d.claimant = gl.message.sender
        d.respondent = respondent
        d.title = title
        d.claimant_argument = argument
        d.claimant_evidence_url = evidence_url
        d.respondent_argument = ""
        d.respondent_evidence_url = ""
        d.respondent_responded = False
        d.verdict = ""
        d.winner = Address("0x0000000000000000000000000000000000000000")
        d.reasoning = ""
        d.status = "OPEN"

        self.disputes[dispute_id] = d

        # Track per-user
        if gl.message.sender not in self.user_disputes:
            self.user_disputes[gl.message.sender] = DynArray[u256]()
        self.user_disputes[gl.message.sender].append(dispute_id)

        if respondent not in self.user_disputes:
            self.user_disputes[respondent] = DynArray[u256]()
        self.user_disputes[respondent].append(dispute_id)

        return dispute_id

    @gl.public.write
    def respond_to_dispute(
        self,
        dispute_id: u256,
        argument: str,
        evidence_url: str = "",
    ) -> None:
        """
        Respondent submits their side of the story.
        After this, arbitration can be triggered.
        """
        assert dispute_id in self.disputes, "Dispute not found"
        d = self.disputes[dispute_id]

        assert gl.message.sender == d.respondent, "Only respondent can respond"
        assert not d.respondent_responded, "Already responded"
        assert d.status == "OPEN", "Dispute is not open"
        assert len(argument) >= 20, "Argument must be at least 20 characters"

        d.respondent_argument = argument
        d.respondent_evidence_url = evidence_url
        d.respondent_responded = True
        self.disputes[dispute_id] = d

    @gl.public.write
    def request_verdict(self, dispute_id: u256) -> None:
        """
        Either party can request AI verdict once both have submitted arguments.
        This is the non-deterministic LLM call.
        """
        assert dispute_id in self.disputes, "Dispute not found"
        d = self.disputes[dispute_id]

        assert d.status == "OPEN", "Dispute already resolved"
        assert d.respondent_responded, "Respondent has not submitted their argument yet"
        assert gl.message.sender in [
            d.claimant, d.respondent
        ], "Only parties can request verdict"

        d.status = "PENDING_VERDICT"
        self.disputes[dispute_id] = d

        # Fetch optional external evidence from web
        claimant_evidence_text = ""
        if d.claimant_evidence_url:
            try:
                result = gl.get_webpage(d.claimant_evidence_url, mode="text")
                claimant_evidence_text = result[:1500]  # cap at 1500 chars
            except:
                claimant_evidence_text = "[Could not fetch claimant evidence URL]"

        respondent_evidence_text = ""
        if d.respondent_evidence_url:
            try:
                result = gl.get_webpage(d.respondent_evidence_url, mode="text")
                respondent_evidence_text = result[:1500]
            except:
                respondent_evidence_text = "[Could not fetch respondent evidence URL]"

        # Build arbitration prompt
        prompt = f"""You are an impartial AI arbitrator resolving a dispute between two parties.

DISPUTE TITLE: {d.title}

CLAIMANT'S ARGUMENT:
{d.claimant_argument}

{"CLAIMANT'S EXTERNAL EVIDENCE:" + chr(10) + claimant_evidence_text if claimant_evidence_text else ""}

RESPONDENT'S ARGUMENT:
{d.respondent_argument}

{"RESPONDENT'S EXTERNAL EVIDENCE:" + chr(10) + respondent_evidence_text if respondent_evidence_text else ""}

---
As an impartial arbitrator, analyze both sides carefully and render a verdict.

Respond ONLY with a valid JSON object in this exact format:
{{
  "winner": "CLAIMANT" or "RESPONDENT" or "DRAW",
  "verdict": "one sentence summary of your decision",
  "reasoning": "2-3 sentence explanation of why you ruled this way, citing the strongest arguments"
}}

Be fair, concise, and base your decision strictly on the arguments provided.
Do not favor either side without reason. If arguments are equally valid, declare DRAW."""

        # Call LLM for verdict
        result = gl.call_llm(prompt)

        # Parse LLM response
        try:
            # Strip markdown if present
            clean = result.strip().strip("```json").strip("```").strip()
            verdict_data = json.loads(clean)

            winner_str = verdict_data.get("winner", "DRAW").upper()
            if winner_str == "CLAIMANT":
                d.winner = d.claimant
            elif winner_str == "RESPONDENT":
                d.winner = d.respondent
            else:
                d.winner = Address("0x0000000000000000000000000000000000000000")

            d.verdict = verdict_data.get("verdict", "Verdict could not be determined.")
            d.reasoning = verdict_data.get("reasoning", "No reasoning provided.")

        except Exception as e:
            d.verdict = result[:300]
            d.reasoning = "Raw LLM response (JSON parse failed)"
            d.winner = Address("0x0000000000000000000000000000000000000000")

        d.status = "RESOLVED"
        self.disputes[dispute_id] = d


@gl.dataclass
class Dispute:
    claimant: Address
    respondent: Address
    title: str
    claimant_argument: str
    claimant_evidence_url: str
    respondent_argument: str
    respondent_evidence_url: str
    respondent_responded: bool
    verdict: str
    winner: Address
    reasoning: str
    status: str  # OPEN | PENDING_VERDICT | RESOLVED
