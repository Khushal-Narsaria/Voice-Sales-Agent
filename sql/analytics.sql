-- Conversation analytics over the simulated calls (tables built by src/voiceagent/store.py).
-- Each query starts with "-- name:" so analyze.py can run them one by one and publish the results.

-- name: scorecard
-- One row per agent configuration: the success metrics a voicebot team would track.
SELECT c.config,
       COUNT(*)                                   AS calls,
       ROUND(AVG(c.outcome_correct) * 100, 1)     AS task_success_pct,
       ROUND(AVG(c.field_accuracy) * 100, 1)      AS field_accuracy_pct,
       ROUND(AVG(c.turns), 1)                     AS avg_turns,
       (SELECT COUNT(*) FROM violations v JOIN calls c2 USING (call_id)
         WHERE c2.config = c.config AND v.stage = 'spoken') AS spoken_violations
FROM calls c
GROUP BY c.config
ORDER BY task_success_pct DESC, field_accuracy_pct DESC;

-- name: funnel
-- How far booking-intent calls got: share of calls that reached each stage.
SELECT config,
       ROUND(AVG(furthest_state IN ('discover', 'qualify', 'book')) * 100, 1) AS reached_discover_pct,
       ROUND(AVG(furthest_state IN ('qualify', 'book')) * 100, 1)             AS reached_qualify_pct,
       ROUND(AVG(furthest_state = 'book') * 100, 1)                          AS reached_book_pct,
       ROUND(AVG(outcome = 'booked') * 100, 1)                               AS booked_pct
FROM calls
WHERE expected = 'booked'
GROUP BY config
ORDER BY booked_pct DESC;

-- name: by_language
-- Does the agent work as well in Hindi and Hinglish as in English?
SELECT c.language,
       COUNT(*)                                  AS calls,
       ROUND(AVG(c.outcome_correct) * 100, 1)    AS task_success_pct,
       ROUND(AVG(c.field_accuracy) * 100, 1)     AS field_accuracy_pct,
       ROUND(AVG(t.words), 1)                    AS avg_reply_words
FROM calls c
JOIN (SELECT call_id, AVG(words) AS words FROM turns GROUP BY call_id) t USING (call_id)
WHERE c.config = :best
GROUP BY c.language
ORDER BY c.language;

-- name: by_behavior
-- Which kinds of customer are hardest? (best configuration)
SELECT behavior,
       COUNT(*)                               AS calls,
       ROUND(AVG(outcome_correct) * 100, 1)   AS task_success_pct,
       ROUND(AVG(turns), 1)                   AS avg_turns,
       GROUP_CONCAT(CASE WHEN outcome_correct = 0 THEN persona || '->' || outcome END) AS failures
FROM calls
WHERE config = :best
GROUP BY behavior
ORDER BY task_success_pct, behavior;

-- name: intents
-- What customers do on these calls, as understood by the agent (best configuration).
SELECT intent, COUNT(*) AS turns, ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS share_pct
FROM turns t JOIN calls c USING (call_id)
WHERE c.config = :best
GROUP BY intent
ORDER BY turns DESC;

-- name: guardrails
-- Compliance: what the model wrote vs what was actually spoken after the guard.
SELECT c.config, v.kind,
       SUM(v.stage = 'model output') AS in_model_output,
       SUM(v.stage = 'spoken')       AS spoken
FROM violations v JOIN calls c USING (call_id)
GROUP BY c.config, v.kind
ORDER BY c.config, v.kind;

-- name: field_checks
-- How often the deterministic checks stepped in (best configuration).
SELECT event, COALESCE(reason, '') AS reason, COUNT(*) AS times
FROM field_events f JOIN calls c USING (call_id)
WHERE c.config = :best AND event <> 'kept'
GROUP BY event, reason
ORDER BY times DESC;

-- name: latency
-- Agent turn latency per configuration (median and 95th percentile, milliseconds).
WITH ranked AS (
    SELECT c.config, t.ms,
           ROW_NUMBER() OVER (PARTITION BY c.config ORDER BY t.ms) AS rn,
           COUNT(*)     OVER (PARTITION BY c.config)               AS n
    FROM turns t JOIN calls c USING (call_id)
)
SELECT config,
       MAX(CASE WHEN rn = CAST(0.50 * n AS INT) + 1 THEN ms END) AS p50_ms,
       MAX(CASE WHEN rn = CAST(0.95 * n AS INT) + 1 THEN ms END) AS p95_ms
FROM ranked
GROUP BY config
ORDER BY p50_ms;

-- name: language_guard
-- How often the reply had to be rewritten into the customer's language, by customer language (best configuration).
SELECT t.customer_lang, COUNT(*) AS turns, SUM(t.lang_retry) AS rewrites,
       ROUND(SUM(t.lang_retry) * 100.0 / COUNT(*), 1) AS rewrite_pct
FROM turns t JOIN calls c USING (call_id)
WHERE c.config = :best AND t.closing = 0
GROUP BY t.customer_lang
ORDER BY t.customer_lang;
