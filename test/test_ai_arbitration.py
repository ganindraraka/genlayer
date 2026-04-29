from gltest import get_contract_factory, default_account
from gltest.assertions import tx_execution_succeeded

RESPONDENT = "0x5e1ff2a30ae8a1f8ebd5a83f56e4f23c1b9c6f3a"

def deploy_contract():
    factory = get_contract_factory("AIArbitration")
    contract = factory.deploy()
    count = contract.get_dispute_count(args=[])
    assert count == 0
    return contract

def test_open_dispute():
    contract = deploy_contract()
    result = contract.open_dispute(
        args=[RESPONDENT, "Freelance Payment Dispute",
        "I delivered the website on time and as agreed, but the client refused to pay the final milestone of $500.", ""]
    )
    assert tx_execution_succeeded(result)
    count = contract.get_dispute_count(args=[])
    assert count == 1
    dispute = contract.get_dispute(args=[0])
    assert dispute["title"] == "Freelance Payment Dispute"
    assert dispute["status"] == "OPEN"

def test_full_arbitration_flow():
    contract = deploy_contract()
    result = contract.open_dispute(
        args=[RESPONDENT, "Service Dispute",
        "I paid for a logo design service but the designer disappeared after receiving 50% upfront payment.", ""]
    )
    assert tx_execution_succeeded(result)
    respond_result = contract.respond_to_dispute(
        args=[0, "I did begin the work and sent 3 initial drafts via email. The client never responded for 2 weeks.", ""],
        wait_interval=5000, wait_retries=10,
    )
    assert tx_execution_succeeded(respond_result)
    verdict_result = contract.request_verdict(
        args=[0], wait_interval=10000, wait_retries=20,
    )
    assert tx_execution_succeeded(verdict_result)
    dispute = contract.get_dispute(args=[0])
    assert dispute["status"] == "RESOLVED"
    print(f"\n✅ Verdict: {dispute['verdict']}")
    print(f"📋 Reasoning: {dispute['reasoning']}")
