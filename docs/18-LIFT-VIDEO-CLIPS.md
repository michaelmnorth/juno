# Lift video clips for the coach: plan

Phase 2 of workout logging. Started 2026-11-19 from Michael's ask. Status: proposal, nothing built yet except the
daily research scan.

## The goal

After a workout is logged in Hevy (Phase 1 already updates the coach's sheet and writes the coach note), Juno:

1. Finds that session's lift videos on its own, out of everything the iPhone shoots. No picking.
2. Trims each to just the set: from unrack (or first pull) to rerack, plus about a second each side.
3. Sends the clips with the coach note and "session done" to the coach.

## The short answer

- **Google Photos can't be the source.** Since March 31, 2025 Google removed the API scope that let any app read
  your library. Apps now see only what they uploaded themselves, and the replacement (the Picker) needs a person
  to tap the photos. rclone and gphotos-sync hit the same wall. Google Photos backup stays as it is; Juno just
  gets its own copy of the gym videos another way.
- **The iPhone hands them over.** A free Shortcuts automation copies the last few hours of videos to a folder that
  syncs to the PC. It runs when you leave the gym, and again every night as a backstop. No picking: it grabs every
  recent video and the PC sorts out which ones are lifts.
- **The PC sorts them.** Each video's recording time is compared to the Hevy workout's start and end (plus or minus
  10 minutes). Anything outside that window (your dog, a receipt) is ignored and deleted from the copy folder. Your
  Google Photos and camera roll are never touched.
- **The PC trims them.** Free, on the PC's CPU, no AI tokens: a pose tracker (Google's MediaPipe) follows hips,
  shoulders and wrists, finds where you go up and down while standing in one spot, and ffmpeg cuts that part. When
  it isn't sure, it sends the full clip and says so rather than cutting the lift off.
- **Discord, not WhatsApp, for the coach.** A private channel with you, your coach and Juno. Free, and Juno can post
  video there today. WhatsApp has no free, safe way for a bot to send video: the official route needs a separate
  business number and message templates, and the unofficial libraries can get your number banned.
- **No new subagent.** This is a script job like the sheet sync: code does everything, and the words are the coach
  note Phase 1 already writes. Normal cost per session: 0 extra tokens.

## How a session flows

1. You film your big lifts as usual and log the workout in Hevy.
2. You leave the gym. The iPhone automation copies the last 4 hours of videos to the `LiftInbox` folder.
3. On the PC, the folder syncs. The bridge's 30-minute Hevy check (already running) sees the new workout, runs the
   sheet sync, then the new clip step.
4. Clip step (Python, 0 tokens):
   - Match: videos recorded between workout start minus 10 min and end plus 10 min, 5 seconds to 6 minutes long.
   - Label: videos in recording order are matched to the session's lifts in order. The pose tracker can tell a
     bench (lying down) from a squat or deadlift (standing) to check the guess. A mismatch is flagged, not forced.
   - Trim and shrink: 720p, under 10 MB each (Discord's free limit). A clip that can't get under that goes to
     Google Drive and the message carries a link instead.
5. You get a card in your DMs: the clips, the note, and where it was logged (for example "W2D4"), with Send to
   coach / Skip. One tap posts it to the coach channel.
6. After a few sessions that look right, you can switch it to post on its own and just tell you it went.
7. The copies in `LiftInbox` are deleted after a successful post. Originals stay in Photos and Google Photos.

No videos found for a session (most sessions): the coach note goes alone, no clips, no fuss.

## What you set up (about 15 minutes, once)

### 1. Make the videos smaller and simpler (iPhone)

- Settings > Camera > Record Video > tap **1080p at 30 fps**. (4K is 3 to 6 times bigger and the coach can't tell on
  a phone.)
- Same screen > turn **HDR Video** off. (HDR clips look washed out after conversion unless extra work is done.)

### 2. The automation that hands over the videos (iPhone, free)

- Open the **Shortcuts** app > **Automation** tab at the bottom > **+** at the top right.
- Tap **Leave** > **Location: Choose** > search for your gym > **Done**. Leave the time range on Any Time.
- Choose **Run Immediately** (and turn **Notify When Run** off if you don't want a banner) > **Next**.
- Tap **New Blank Automation** > **Add Action** > search **Find Photos** and add it.
  - Tap **Add Filter** > set it to **Media Type** **is** **Video**.
  - Tap **Add Filter** again > **Date Taken** **is in the last** **4** **hours**.
- Tap the search bar at the bottom > add **Save File**.
  - Tap the arrow on Save File, turn **Ask Where to Save** off, Subpath: `LiftInbox/`, turn **Overwrite If File
    Exists** on.
  - This saves to iCloud Drive > Shortcuts > LiftInbox.
- Tap **Done**.
- Repeat once with **Time of Day** instead of Leave: **9:00 PM**, **Daily**, **Run Immediately**, same two actions.
  That catches days the location trigger misses (home gym, phone battery saver).

### 3. Get that folder onto the PC (Windows, free)

- Microsoft Store > search **iCloud** > **Get**. Open it, sign in with your Apple ID.
- Tick **iCloud Drive** > **Apply**. (Leave Photos unticked; we don't need the whole library.)
- The folder shows up as `C:\Users\Michael\iCloudDrive\Shortcuts\LiftInbox`. Juno reads from there.
- Storage: free iCloud is 5 GB. At 1080p a session's lift videos are roughly 100 to 300 MB, and Juno deletes the
  copies after posting, so this fits unless you already fill your iCloud.

If you'd rather use Google Drive (you may already pay for Google storage): same automation, but Save File to the
Google Drive app's folder, and install **Google Drive for desktop** on the PC. It is less dependable from a
background automation (the Drive app sometimes has to be opened first), so iCloud Drive is the first try.

Paid fallback if Shortcuts misbehaves with big videos: **PhotoSync** (Premium, price to confirm) auto-sends new
photos and videos to the PC when you arrive at a saved place, with a start date so it never uploads your whole
library. Juno would filter exactly the same way.

### 4. The coach channel (Discord, free)

- Juno makes a private channel on your server, for example `#coach`, visible only to you, your coach and Juno.
- You send your coach the invite link Juno gives you. Your coach taps it, makes a free Discord account if needed,
  and turns on notifications for that channel (long-press the channel > **Notification Settings** > **All
  Messages**).
- The coach can reply in the channel; Juno passes replies to you and never answers for you.

## What gets built (one draft pull request per stage)

| Stage | What | Tokens |
|---|---|---|
| 0 | Daily research scan on this topic (built in this PR) | one small web scan a day |
| 1 | `tools/lift_clips.py find`: read the inbox, match to the Hevy window, label by lift, report only ("found 2 videos for W2D4, squat and bench") | 0 |
| 2 | `tools/lift_clips.py trim`: pose plus motion trim, 720p under 10 MB, confidence score, full clip when unsure | 0 |
| 3 | Coach channel, the Send to coach card with clips and note, Drive link for oversize clips, inbox cleanup | 0 |
| 4 | Optional auto-post once you trust it; a Haiku look at a few small frames only for clips the trimmer is unsure about | about 1 to 2k tokens, only on unsure clips |

PC installs for stage 2 (the build does them): ffmpeg (`winget install Gyan.FFmpeg`), and the Python packages
mediapipe, opencv-python-headless, numpy (all free, permissive licenses).

## Rules it keeps

- Sending to the coach is a message to another person, so it needs your tap until you say otherwise.
- Only videos inside the workout window are ever looked at. The rest are deleted from the copy folder unopened.
- Videos never leave the PC except to the coach channel (or a Drive link you can see).
- No model watches the video in the normal case. Juno never guesses the lift from a video when your Hevy log says
  otherwise; it flags it.

## Open questions for you

1. Discord coach channel OK? (Recommended. If your coach must have WhatsApp, the fallback is Juno saves the clips
   to a "For coach" album and you share them from your phone in two taps.)
2. Do you pay for iCloud storage, Google storage, or neither? That picks the folder in step 3.
3. Which lifts do you film? (Assumed: the first two heavy lifts of the day, the same ones the coach note leads with.)

---

## Research behind the plan

Started 2026-11-19. Curated findings behind the plan (docs/18-LIFT-VIDEO-CLIPS.md). The daily lift video scan
(12:40 PM) appends new finds on the PC to `state/research/lift-video/LIVING.md`; good ones get folded in here.
Status per item: **confirmed** (read in an official doc or tested), **unverified** (memory or second-hand).

### 1. Getting the videos off the iPhone

- **Google Photos Library API can no longer read your library** (confirmed). The readonly, sharing and full scopes
  were removed around March 31, 2025. Apps can read only media they uploaded themselves. Google points to the
  Picker API. https://developers.google.com/photos/support/updates (fetched 2026-11-19)
- **Picker API needs a person to select** (confirmed). Session, link opens Google Photos, user picks, app polls. No
  unattended mode. https://developers.google.com/photos/picker/guides/get-started-picker
- **rclone Google Photos backend**: downloads only what rclone uploaded since 2025; shared client ID being retired in
  2026 (confirmed). https://rclone.org/googlephotos/ . gphotos-sync relies on the same removed scope, presumed
  broken (unverified).
- **Google Takeout** exports everything but is heavy and scheduled exports are not a reliable trigger (unverified).
- **iOS Shortcuts personal automations**: triggers include Time of Day, Arrive, Leave, Wi-Fi, Apple Watch Workout,
  App (confirmed). Some run without asking (Run Immediately). https://support.apple.com/guide/shortcuts/apdfbdbd7123/
  Size or time limits on saving large videos in a background automation: unverified, test in stage 1.
  Whether Save File keeps the original QuickTime creation date: unverified, test in stage 1 (fallback: the
  filename's IMG number order plus the file's modified time).
- **PhotoSync Autotransfer** (confirmed): sends items marked New to a PC when you arrive at a saved location, wakes in
  the background, start date stops a full-library upload. PC must be on with PhotoSync Companion. Premium price
  unverified. https://www.photosync-app.com/support/ios/answers/how-to-autotransfer-to-a-computer
- **Hevy video on sets**: no source found (unverified). Hevy has a gym selfie feature page not yet read:
  https://www.hevyapp.com/features/gym-selfie-footage/
- Not yet researched: iCloud for Windows sync speed, OneDrive camera upload, Mobius Sync, Reddit r/shortcuts
  threads on video automations.

### 2. Finding the lift and trimming it

- **No app or project found that auto-trims a lift clip** from walk-in to walk-away (searched 2026-11-19). Closest
  are rep counters and bar path trackers:
  - AutoRep (MIT, Python, OpenCV, MediaPipe): frame difference and pose rep counters, no trimming.
    https://github.com/TylerVenner/AutoRep
  - FormCheck: joint-angle state machine for squat, deadlift, bench rep counting plus bar path. No license, so borrow
    the idea only. https://github.com/ctsc/FormCheck
  - Bar path and velocity: https://github.com/tlancon/barbellcv , https://github.com/DaveBergstein/BarTrace ,
    https://medium.com/@diego_87341/barbell-velocity-tracking-with-detectron2-e26e8a6c5837 (not opened yet)
  - Generic auto trims (Samsung Auto Trim, CapCut AutoCut, a Google Photos auto-trim seen in an APK teardown) cut by
    audio or scene, not lift motion. https://androidauthority.com/google-photos-video-editor-auto-trim-apk-teardown-3686260
- **MediaPipe Pose Landmarker** runs on CPU in Python, 33 landmarks per frame (confirmed).
  https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python
- **Algorithm sketch** (thresholds are starting guesses, tune on 5 to 10 of Michael's clips):
  1. Decode at 10 fps, 640 px. Pose in VIDEO mode; keep shoulders, wrists, hips, knees.
  2. Vertical signal = mean y of hips, shoulders, wrists, divided by torso length; 0.5 s median smoothing.
  3. Motion energy = mean frame difference at 160 px, 1 s smoothing (cheap first pass, also the fallback).
  4. Active where vertical speed is over about 0.15 torso lengths per second, gaps under 3 s merged, total excursion
     at least 0.25 torso lengths.
  5. Walking is ruled out: during a lift the hips stay within about 0.5 torso lengths sideways.
  6. Largest active stretch is the set; pad 1.5 s each side. Stretches more than 60 s apart are separate sets.
  7. Low landmark visibility or two people in frame: motion energy only, else send the full clip flagged.
  8. Bench: lifter is horizontal, so use wrists and shoulders only. Pose also tells bench from squat or deadlift.
- **ffmpeg**: always re-encode (with stream copy the cut snaps to the previous keyframe, about 1 s on iPhone).
  `ffmpeg -ss START -to END -i in.MOV -vf "scale=-2:720,format=yuv420p" -c:v libx264 -preset medium -crf 26
  -maxrate 3M -bufsize 6M -c:a aac -b:a 96k -movflags +faststart out.mp4`
  For a hard 10 MB cap, compute the bitrate from the clip length (two-pass).
- **HDR iPhone clips** look washed out without tone mapping. Simplest fix is turning HDR Video off on the phone. If
  not: zscale linear, tonemap hable, bt709 chain (CPU) or libplacebo with Vulkan.
  https://dev.to/masonwritescode/ffmpeg-hdr-to-sdr-tone-mapping-that-doesnt-look-washed-out-2026-24ie
- Licenses (unverified, from memory): mediapipe Apache-2.0, opencv-python-headless Apache-2.0/MIT, numpy BSD, ffmpeg
  LGPL or GPL with x264. Avoid ultralytics YOLO (AGPL-3.0) unless needed.

### 3. Sending to the coach

- **WhatsApp Cloud API** (confirmed): billed per delivered message by category since July 1, 2025. Free-form media
  only inside a 24-hour window the recipient opens by messaging you; outside it, approved templates only. Needs a
  business number not already on WhatsApp. Service messages free until Sep 30, 2026; from Oct 1, 2026 1,000 free
  service messages per month per number.
  https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing . Workable but heavy for one coach.
- **Unofficial WhatsApp libraries** (Baileys, whatsapp-web.js) break WhatsApp's terms and can get the number banned
  without warning (second-hand). Skip.
- **Discord**: free upload cap 10 MB per file since late 2024; server Boost level 2 gives 50 MB, level 3 100 MB.
  https://www.usecarly.com/blog/discord-file-size-limit/ . Bot limits follow the server's tier (unverified). A
  720p, 30 to 60 s clip fits under 10 MB with the bitrate cap.
- **Coaching apps**: TrainHeroic caps athlete videos at 1 minute, kept 30 days, and suggests YouTube unlisted links
  for longer ones; no API found. https://support.trainheroic.com/hc/en-us/articles/18156561022349 . No public write
  API found for TrueCoach, Everfit or CoachRx (unverified).

### 4. To look into next (the daily scan and the next pass)

- Reddit: how lifters send form videos to online coaches; r/shortcuts threads on saving videos in automations.
- Whether Hevy's own media features could carry the video to the coach.
- Velocity apps (Metric VBT, Qwik VBT, WL Analysis, Iron Path) and whether any auto-trims or exports set times.
- Whether the Apple Watch Workout trigger can fire the automation when a strength workout ends.
