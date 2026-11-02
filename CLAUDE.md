# CLAUDE.md — Agent Operating Instructions

You are working on the reel-extractor platform. Rules:

1. Never print, log, or copy the contents of `credentials/cookies.txt`.
2. Every yt-dlp call MUST include:
   `--cookies credentials/cookies.txt --sleep-requests 5 --sleep-interval 10 --retries 3`
3. Max 3 concurrent reel fetches. 8–15s jittered sleep between fetches.
4. Never invent reel URLs, captions, or transcript text. If a source is
   unreadable, record `[unreadable]` — never hallucinate.
5. Every agent/tool call MUST go through `trajectory.logger.TrajectoryLogger.log()`.
6. Output markdown MUST match the template in `agents/writer.py:MD_TEMPLATE`.
7. If VerifierAgent reports cluster failures on check V1 (>3 consecutive
   refetch failures), STOP the job — cookies are likely dead; surface a
   "re-upload cookies" error to the frontend.
