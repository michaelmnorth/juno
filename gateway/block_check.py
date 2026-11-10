"""Post one throwaway DM to Michael that exercises the Block Kit pieces docs/14 lists as unconfirmed.

Checks: strikethrough in section mrkdwn, `>` quotes, rich_text_preformatted, a two-column fields grid, a context line
with a text character instead of an image, and a url button (action_id edit_link, which the bridge already acks).
Slack rejects invalid blocks with an error, so a clean post means the blocks are accepted; how they render is checked
by eye. Uses the bridge's own token loader and allowlist; posts only to Michael.

    python gateway/block_check.py           # the docs/14 checks
    python gateway/block_check.py --brief   # a sample morning brief card (fake data)
    python gateway/block_check.py --checkin | --reflection   # sample screens 4 and 5 (fake data)
    python gateway/block_check.py --status | --home          # screens 4 and 6 from real state/
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import slack_bridge  # noqa: E402

BLOCKS = [
    {"type": "header", "text": {"type": "plain_text", "text": "Block test (safe to ignore)"}},
    {"type": "section", "text": {"type": "mrkdwn", "text": "1. Strikethrough: ~Okay to invite Dana to the market, Saturday 10 to 12?~"}},
    {"type": "section", "text": {"type": "mrkdwn", "text": "2. Quote:\n> Before: Never ping about newsletters.\n> After: Batch newsletters into the evening check-in."}},
    {"type": "rich_text", "elements": [
        {"type": "rich_text_section", "elements": [{"type": "text", "text": "3. Preformatted:"}]},
        {"type": "rich_text_preformatted", "elements": [{"type": "text", "text": "Hey Dana!\n\nSaturday works. See you at 10.\n\nRegards,\nMichael"}]},
    ]},
    {"type": "section", "fields": [
        {"type": "mrkdwn", "text": "*Who*\nDana, a friend"},
        {"type": "mrkdwn", "text": "*Why*\nShe asked about Saturday"},
        {"type": "mrkdwn", "text": "*What*\nCalendar invite"},
        {"type": "mrkdwn", "text": "*Expires*\n10:30 AM"},
    ]},
    {"type": "context", "elements": [{"type": "mrkdwn", "text": "⏱ 4. Context line with a text character, no image"}]},
    {"type": "actions", "elements": [
        {"type": "button", "action_id": "edit_link", "text": {"type": "plain_text", "text": "5. Link button"},
         "url": "https://mail.google.com/mail/u/0/#drafts"},
    ]},
]


SAMPLE_BRIEF = {
    "headline": "Sample brief (fake data). Light day.",
    "counts": "3 need you · 2 events · slept 7h 05m",
    "needs_you": [
        {"text": "Dana asked about Saturday; reply drafted, below."},
        {"text": "Electric bill due Thursday, $84. Autopay is off for this one."},
        {"text": "Sample bank alert at 6:25 AM: a $120 card purchase.", "url": "https://mail.google.com/mail/u/0/#inbox"},
    ],
    "today": [
        {"time": "12:30", "text": "Lunch with Dana, Juniper Cafe", "prep": "Leave by 12:05. Ask how the move went.",
         "url": "https://maps.google.com/?q=Juniper+Cafe"},
        {"time": "17:30", "text": "Squat day", "prep": "Coach moved the top set to 3 reps."},
    ],
    "busy": ["2 newsletters", "1 receipt", "A shipping update"],
    "remembered": [{"text": "You cut the greeting on business drafts."}],
    "watching": "Two videos on agent memory; one idea for Juno saved to notes.",
}


SAMPLE_CHECKIN = {
    "headline": "Sample check-in (fake data). Tomorrow starts at 9:30",
    "tomorrow": [{"time": "9:30", "text": "Dentist, Midtown", "prep": "Bring the insurance card.", "button": "prep"}],
    "still_open": [{"text": "Reply to Sam about the game, drafted this morning.", "button": "review"}],
    "quiet_mail": ["Sample newsletter", "Sample receipt, $12"],
    "remembered": [{"text": "You train before work on Tuesdays.", "seen": "Seen 3 times · from your calendar"}],
    "question": {"text": "Trained today?", "answers": ["Trained", "Rest day", "Skipped"]},
}

SAMPLE_REFLECTION = {
    "title": "Sample week (fake data, don't tap Save)",
    "summary": {"runs": "41 (2 failed)", "blocked": 3, "spent": "$4.10"},
    "changes": [
        {"id": "sample-1", "target": "learnings/drafter.md", "old_line": "",
         "new_line": "- 2026-11-08: Cut the greeting on business drafts. (sample)", "evidence": "You edited 3 of 4 drafts this way"},
        {"id": "sample-2", "target": "me/preferences.md", "old_line": "- 2026-11-01: Ping about newsletters. (sample)",
         "new_line": "- 2026-11-08: Batch newsletters into the evening check-in. (sample)", "evidence": "You ignored 5 newsletter pings"},
    ],
    "watching": {"themes": "Agent memory and Slack apps", "ideas": ["A Home tab that shows this week's spend"]},
    "coming_up": [{"text": "Sam's birthday in 6 days", "note": "Last year: concert tickets", "button": "ideas"}],
}


def main() -> int:
    if not slack_bridge.load_tokens_with_retry(attempts=1):
        return 2
    from slack_bolt import App
    import json
    import os
    app = App(token=os.environ["SLACK_BOT_TOKEN"])
    bridge = slack_bridge.Bridge()
    if "--brief" in sys.argv:  # the morning brief card, drawn from fake data the way the 7:00 job draws it
        ts = slack_bridge.post_job(app.client, bridge, "morning-brief", json.dumps(SAMPLE_BRIEF))
        print(f"posted ts={ts}" if ts else "not posted")
        return 0 if ts else 1
    if "--checkin" in sys.argv or "--reflection" in sys.argv:
        job, data = (("evening-checkin", SAMPLE_CHECKIN) if "--checkin" in sys.argv
                     else ("weekly-reflection", SAMPLE_REFLECTION))
        ts = slack_bridge.post_job(app.client, bridge, job, json.dumps(data))
        print(f"posted ts={ts}" if ts else "not posted")
        return 0 if ts else 1
    if "--status" in sys.argv:  # real state, no Claude run
        msg = slack_bridge.cards.status_blocks(bridge.root, slack_bridge.load_proactivity(bridge.root))
        ts = slack_bridge.post_to_michael(app.client, bridge, msg.text, msg.blocks)
        print(f"posted ts={ts}" if ts else "not posted")
        return 0 if ts else 1
    if "--home" in sys.argv:  # real state, as the "home" reply draws it
        channel = slack_bridge.open_dm(app.client, sorted(bridge.allowlist)[0])
        view = slack_bridge.cards.home_view(bridge.root, slack_bridge.load_proactivity(bridge.root),
                                            slack_bridge.home_links(app.client, bridge, channel))
        ts = slack_bridge.post_to_michael(app.client, bridge, view["blocks"][1]["text"]["text"], view["blocks"][:50])
        print(f"posted ts={ts}" if ts else "not posted")
        return 0 if ts else 1
    ts = slack_bridge.post_to_michael(app.client, bridge, "Block test (safe to ignore)", BLOCKS)
    print(f"posted ts={ts}" if ts else "not posted")
    return 0 if ts else 1


if __name__ == "__main__":
    sys.exit(main())
