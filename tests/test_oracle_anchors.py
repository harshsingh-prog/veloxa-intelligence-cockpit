"""The oracle is an independent parser; these hand-verified numbers (from the first manual inspection of the data room)
make sure it - and therefore the whole evaluation - cannot silently drift."""
from eval.oracle import O


def test_hand_verified_anchors():
    o = O()
    assert (o["jira_total"], o["jira_done"], o["jira_open"], o["jira_pts"], o["jira_inprog"], o["jira_todo"]) == (62, 35, 27, 115, 8, 19)
    assert o["by"] == {"PN": (14, 62), "RV": (7, 25), "AD": (2, 10), "SK": (4, 18)}
    assert (o["inc_n"], o["sev1_n"], o["sev1_aug"]) == (11, 3, 3)
    assert (o["arr3"], o["burn3"], o["runway3"], o["cust3"]) == ("Rs. 6.1 Cr", "Rs. 44 L", "13 months", 66)
    assert (o["mkt_total"], o["mkt_evt"], o["mkt_ps"]) == (1426620, 1003000, 423620)
    assert o["emp_n"] == 19 and o["agents_n"] == 14
    assert o["pulse"]["Engineering"] == 3.1 and o["pulse"]["Marketing"] == 3.4
    assert o["held"] == ["REQ-014", "REQ-015"]
    assert (o["ga_orig"], o["ga_new"], o["ga_changed"]) == ("2026-09-15", "2026-12-15", "2026-09-02")
    assert o["commits"]["priya.n@veloxa.in"] == 425 and o["commits"]["pnair@users.noreply.github.com"] == 163 and sum(o["commits"].values()) == 1453
    assert (o["rahul_days_payable"], o["rahul_days_month"], o["feb_processor"]) == (28, 28, "KS")
