-- ============================================================================
-- STUDENT PERFORMANCE FACTORS — FULL SQL ANALYTICAL STUDY
-- Dataset : StudentPerformanceFactors.csv (6,607 students × 20 features)
-- Dialect : PostgreSQL 15+ (uses FILTER, WITHIN GROUP, window functions)
-- Author  : Haley Maes
-- Purpose : End-to-end SQL analytical study translating raw survey & registrar
--           exports into:
--             1. Audited & mode-imputed analytical view (vw_student_factors_clean)
--             2. Engineered indices, window rankings & 4-cohort segmentation
--                (vw_student_analytical_profile)
--             3. Unified 19-feature driver leaderboard (score spread + Pearson r)
--             4. Early-warning advising queue surfacing "Drifting High-Potential"
--                students missed by prior-score filters (vw_advising_triage_queue)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- SECTION 1: STAGING TABLE DEFINITION
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS raw_student_performance CASCADE;

CREATE TABLE raw_student_performance (
    hours_studied              INT,
    attendance                 INT,
    parental_involvement       TEXT,
    access_to_resources        TEXT,
    extracurricular_activities TEXT,
    sleep_hours                INT,
    previous_scores            INT,
    motivation_level           TEXT,
    internet_access            TEXT,
    tutoring_sessions          INT,
    family_income              TEXT,
    teacher_quality            TEXT,
    school_type                TEXT,
    peer_influence             TEXT,
    physical_activity          INT,
    learning_disabilities      TEXT,
    parental_education_level   TEXT,
    distance_from_home         TEXT,
    gender                     TEXT,
    exam_score                 INT
);

-- Load via psql:
-- \copy raw_student_performance FROM 'data/StudentPerformanceFactors.csv' WITH (FORMAT csv, HEADER true, NULL '');


-- ----------------------------------------------------------------------------
-- SECTION 2: DATA QUALITY & COMPLETENESS AUDIT
-- Checks row count (6,607), range violations (1 record with exam_score = 101),
-- and missing values across all 20 columns (235 total nulls across 3 columns).
-- ----------------------------------------------------------------------------
SELECT
    COUNT(*)                                                                AS total_students,
    COUNT(*) FILTER (WHERE exam_score > 100 OR exam_score < 0)              AS out_of_range_scores,
    MIN(exam_score)                                                         AS min_raw_exam_score,
    MAX(exam_score)                                                         AS max_raw_exam_score,
    COUNT(*) FILTER (WHERE parental_education_level IS NULL)                AS null_parental_ed,
    ROUND(100.0 * COUNT(*) FILTER (WHERE parental_education_level IS NULL)
          / COUNT(*), 2)                                                    AS null_parental_ed_pct,
    COUNT(*) FILTER (WHERE teacher_quality IS NULL)                         AS null_teacher_quality,
    ROUND(100.0 * COUNT(*) FILTER (WHERE teacher_quality IS NULL)
          / COUNT(*), 2)                                                    AS null_teacher_quality_pct,
    COUNT(*) FILTER (WHERE distance_from_home IS NULL)                      AS null_distance,
    ROUND(100.0 * COUNT(*) FILTER (WHERE distance_from_home IS NULL)
          / COUNT(*), 2)                                                    AS null_distance_pct
FROM raw_student_performance;


-- ----------------------------------------------------------------------------
-- SECTION 3: CLEANED & ENCODED ANALYTICAL VIEW (vw_student_factors_clean)
-- 1. Assigns deterministic student_id via ROW_NUMBER()
-- 2. Caps impossible exam_score > 100 to 100 (1 row: 101 -> 100)
-- 3. Imputes the 3 nullable categorical columns using SQL statistical mode
--    (MODE() WITHIN GROUP (ORDER BY col))
-- 4. Encodes ordinal scales (0/1/2) and binary indicators (0/1) for SQL math
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_student_factors_clean AS
WITH modal_defaults AS (
    SELECT
        MODE() WITHIN GROUP (ORDER BY teacher_quality)          AS mode_teacher_quality,
        MODE() WITHIN GROUP (ORDER BY parental_education_level) AS mode_parental_ed,
        MODE() WITHIN GROUP (ORDER BY distance_from_home)       AS mode_distance
    FROM raw_student_performance
)
SELECT
    ROW_NUMBER() OVER (
        ORDER BY r.exam_score DESC, r.attendance DESC, r.hours_studied DESC, r.previous_scores DESC
    )                                                                       AS student_id,
    r.hours_studied,
    r.attendance,
    r.previous_scores,
    r.sleep_hours,
    r.tutoring_sessions,
    r.physical_activity,
    LEAST(GREATEST(r.exam_score, 0), 100)                                   AS exam_score,

    -- Cleaned categoricals (mode-imputed where NULL)
    r.parental_involvement,
    r.access_to_resources,
    r.motivation_level,
    r.family_income,
    COALESCE(r.teacher_quality, m.mode_teacher_quality)                     AS teacher_quality,
    r.peer_influence,
    COALESCE(r.parental_education_level, m.mode_parental_ed)                AS parental_education_level,
    COALESCE(r.distance_from_home, m.mode_distance)                         AS distance_from_home,
    r.extracurricular_activities,
    r.internet_access,
    r.school_type,
    r.learning_disabilities,
    r.gender,

    -- Ordinal encodings (0 = Low/Negative/HS/Near, 1 = Mid, 2 = High/Positive/Postgrad/Far)
    CASE r.parental_involvement
        WHEN 'Low' THEN 0 WHEN 'Medium' THEN 1 WHEN 'High' THEN 2 END      AS parental_involvement_enc,
    CASE r.access_to_resources
        WHEN 'Low' THEN 0 WHEN 'Medium' THEN 1 WHEN 'High' THEN 2 END      AS access_to_resources_enc,
    CASE r.motivation_level
        WHEN 'Low' THEN 0 WHEN 'Medium' THEN 1 WHEN 'High' THEN 2 END      AS motivation_level_enc,
    CASE r.family_income
        WHEN 'Low' THEN 0 WHEN 'Medium' THEN 1 WHEN 'High' THEN 2 END      AS family_income_enc,
    CASE COALESCE(r.teacher_quality, m.mode_teacher_quality)
        WHEN 'Low' THEN 0 WHEN 'Medium' THEN 1 WHEN 'High' THEN 2 END      AS teacher_quality_enc,
    CASE r.peer_influence
        WHEN 'Negative' THEN 0 WHEN 'Neutral' THEN 1 WHEN 'Positive' THEN 2 END AS peer_influence_enc,
    CASE COALESCE(r.parental_education_level, m.mode_parental_ed)
        WHEN 'High School' THEN 0 WHEN 'College' THEN 1 WHEN 'Postgraduate' THEN 2 END AS parental_ed_enc,
    CASE COALESCE(r.distance_from_home, m.mode_distance)
        WHEN 'Near' THEN 0 WHEN 'Moderate' THEN 1 WHEN 'Far' THEN 2 END    AS distance_enc,

    -- Binary encodings (0 / 1)
    CASE WHEN r.internet_access = 'Yes' THEN 1 ELSE 0 END                   AS internet_access_enc,
    CASE WHEN r.extracurricular_activities = 'Yes' THEN 1 ELSE 0 END        AS extracurricular_enc,
    CASE WHEN r.school_type = 'Private' THEN 1 ELSE 0 END                   AS private_school_enc,
    CASE WHEN r.learning_disabilities = 'Yes' THEN 1 ELSE 0 END             AS learning_disability_enc,
    CASE WHEN r.gender = 'Female' THEN 1 ELSE 0 END                         AS female_enc
FROM raw_student_performance AS r
CROSS JOIN modal_defaults AS m;


-- ----------------------------------------------------------------------------
-- SECTION 4: FEATURE ENGINEERING, WINDOW RANKINGS & COHORT SEGMENTATION
-- Builds composite indices in SQL, evaluates each student relative to their
-- school_type × family_income peer group using window functions, and assigns
-- every student to one of four actionable behavioral cohorts.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_student_analytical_profile AS
WITH engineered AS (
    SELECT
        c.*,
        -- Effort-to-rest ratio: weekly study hours per hour of nightly sleep (+1 smoothing)
        ROUND(c.hours_studied::NUMERIC / NULLIF(c.sleep_hours + 1, 0), 2)   AS productivity_ratio,

        -- Weighted academic momentum index (prior baseline + current attendance & study habits)
        ROUND(
            0.50 * c.previous_scores
          + 0.30 * c.attendance
          + 0.20 * c.hours_studied,
            2
        )                                                                   AS academic_momentum,

        -- Socioeconomic & home access composite (0 to 6 scale)
        (c.family_income_enc + c.access_to_resources_enc
         + c.internet_access_enc + c.private_school_enc)                    AS socioeconomic_score,

        -- Instructional & family support network (0 to 6+ scale)
        (c.parental_involvement_enc + c.teacher_quality_enc
         + LEAST(c.tutoring_sessions, 3))                                   AS support_network_score,

        -- Wellness & optimal sleep indicator (7-9h optimal sleep + weekly physical activity)
        (c.physical_activity
         + CASE WHEN c.sleep_hours BETWEEN 7 AND 9 THEN 2 ELSE 0 END)       AS wellness_score,

        -- At-risk flag (bottom tertile threshold: exam_score <= 65, 32.3% of cohort)
        CASE WHEN c.exam_score <= 65 THEN 1 ELSE 0 END                      AS is_at_risk,

        -- Performance band classification
        CASE
            WHEN c.exam_score <= 62 THEN '1_Below Avg (<=62)'
            WHEN c.exam_score <= 66 THEN '2_Average (63-66)'
            WHEN c.exam_score <= 70 THEN '3_Above Avg (67-70)'
            ELSE                         '4_Excellent (71+)'
        END                                                                 AS performance_band,

        -- Actionable 4-segment behavioral & prior-score cohort classification
        CASE
            WHEN c.attendance >= 85 AND c.hours_studied >= 20
                THEN 'High-Discipline Anchors'
            WHEN c.previous_scores >= 80 AND (c.attendance < 80 OR c.hours_studied < 18)
                THEN 'Drifting High-Potential'
            WHEN c.attendance < 75 AND c.hours_studied < 20
                THEN 'Disengaged At-Risk'
            ELSE 'Steady Middle'
        END                                                                 AS cohort_segment
    FROM vw_student_factors_clean AS c
)
SELECT
    e.*,
    -- Window functions: overall percentile, momentum quartile, and peer-group score delta
    ROUND(100.0 * PERCENT_RANK() OVER (ORDER BY e.exam_score)::NUMERIC, 1)  AS exam_percentile,
    NTILE(4) OVER (ORDER BY e.academic_momentum)                            AS momentum_quartile,
    NTILE(4) OVER (ORDER BY e.attendance)                                   AS attendance_quartile,
    NTILE(4) OVER (ORDER BY e.hours_studied)                                AS study_hours_quartile,
    ROUND(
        e.exam_score
        - AVG(e.exam_score) OVER (PARTITION BY e.school_type, e.family_income),
        2
    )                                                                       AS score_vs_income_school_peers
FROM engineered AS e;


-- ----------------------------------------------------------------------------
-- SECTION 5: UNIFIED 19-FEATURE DRIVER LEADERBOARD
-- Ranks all 19 explanatory variables on the same SQL yardstick:
--   1. Pearson correlation (CORR) with cleaned exam_score
--   2. Mean exam_score in Top Tier vs. Bottom Tier (Q4 vs Q1 for numeric;
--      highest vs lowest category for ordinal/binary)
--   3. Score spread (Top Tier minus Bottom Tier)
--   4. At-Risk rate (exam_score <= 65) in Bottom Tier vs Top Tier
-- ----------------------------------------------------------------------------
WITH base AS (
    SELECT
        p.*,
        NTILE(4) OVER (ORDER BY p.previous_scores)    AS prev_q,
        NTILE(4) OVER (ORDER BY p.physical_activity)  AS phys_q,
        NTILE(4) OVER (ORDER BY p.sleep_hours)        AS sleep_q
    FROM vw_student_analytical_profile AS p
),
feature_comparisons AS (
    SELECT 'Attendance (Q4 vs Q1)' AS feature_name, 'Behavioral' AS domain,
           CORR(exam_score, attendance) AS pearson_r,
           AVG(exam_score) FILTER (WHERE attendance_quartile = 4) AS top_tier_mean,
           AVG(exam_score) FILTER (WHERE attendance_quartile = 1) AS low_tier_mean,
           100.0 * AVG(is_at_risk) FILTER (WHERE attendance_quartile = 1) AS low_tier_risk_pct,
           100.0 * AVG(is_at_risk) FILTER (WHERE attendance_quartile = 4) AS top_tier_risk_pct
    FROM base
    UNION ALL
    SELECT 'Hours_Studied (Q4 vs Q1)', 'Behavioral',
           CORR(exam_score, hours_studied),
           AVG(exam_score) FILTER (WHERE study_hours_quartile = 4),
           AVG(exam_score) FILTER (WHERE study_hours_quartile = 1),
           100.0 * AVG(is_at_risk) FILTER (WHERE study_hours_quartile = 1),
           100.0 * AVG(is_at_risk) FILTER (WHERE study_hours_quartile = 4)
    FROM base
    UNION ALL
    SELECT 'Access_to_Resources (High vs Low)', 'Socioeconomic & Support',
           CORR(exam_score, access_to_resources_enc),
           AVG(exam_score) FILTER (WHERE access_to_resources = 'High'),
           AVG(exam_score) FILTER (WHERE access_to_resources = 'Low'),
           100.0 * AVG(is_at_risk) FILTER (WHERE access_to_resources = 'Low'),
           100.0 * AVG(is_at_risk) FILTER (WHERE access_to_resources = 'High')
    FROM base
    UNION ALL
    SELECT 'Previous_Scores (Q4 vs Q1)', 'Academic Baseline',
           CORR(exam_score, previous_scores),
           AVG(exam_score) FILTER (WHERE prev_q = 4),
           AVG(exam_score) FILTER (WHERE prev_q = 1),
           100.0 * AVG(is_at_risk) FILTER (WHERE prev_q = 1),
           100.0 * AVG(is_at_risk) FILTER (WHERE prev_q = 4)
    FROM base
    UNION ALL
    SELECT 'Parental_Involvement (High vs Low)', 'Socioeconomic & Support',
           CORR(exam_score, parental_involvement_enc),
           AVG(exam_score) FILTER (WHERE parental_involvement = 'High'),
           AVG(exam_score) FILTER (WHERE parental_involvement = 'Low'),
           100.0 * AVG(is_at_risk) FILTER (WHERE parental_involvement = 'Low'),
           100.0 * AVG(is_at_risk) FILTER (WHERE parental_involvement = 'High')
    FROM base
    UNION ALL
    SELECT 'Tutoring_Sessions (3+ vs 0/mo)', 'Academic Support',
           CORR(exam_score, tutoring_sessions),
           AVG(exam_score) FILTER (WHERE tutoring_sessions >= 3),
           AVG(exam_score) FILTER (WHERE tutoring_sessions = 0),
           100.0 * AVG(is_at_risk) FILTER (WHERE tutoring_sessions = 0),
           100.0 * AVG(is_at_risk) FILTER (WHERE tutoring_sessions >= 3)
    FROM base
    UNION ALL
    SELECT 'Learning_Disabilities (No vs Yes)', 'Personal & Health',
           CORR(exam_score, -learning_disability_enc),
           AVG(exam_score) FILTER (WHERE learning_disabilities = 'No'),
           AVG(exam_score) FILTER (WHERE learning_disabilities = 'Yes'),
           100.0 * AVG(is_at_risk) FILTER (WHERE learning_disabilities = 'Yes'),
           100.0 * AVG(is_at_risk) FILTER (WHERE learning_disabilities = 'No')
    FROM base
    UNION ALL
    SELECT 'Parental_Education (Postgrad vs HS)', 'Socioeconomic & Support',
           CORR(exam_score, parental_ed_enc),
           AVG(exam_score) FILTER (WHERE parental_education_level = 'Postgraduate'),
           AVG(exam_score) FILTER (WHERE parental_education_level = 'High School'),
           100.0 * AVG(is_at_risk) FILTER (WHERE parental_education_level = 'High School'),
           100.0 * AVG(is_at_risk) FILTER (WHERE parental_education_level = 'Postgraduate')
    FROM base
    UNION ALL
    SELECT 'Peer_Influence (Positive vs Negative)', 'School Environment',
           CORR(exam_score, peer_influence_enc),
           AVG(exam_score) FILTER (WHERE peer_influence = 'Positive'),
           AVG(exam_score) FILTER (WHERE peer_influence = 'Negative'),
           100.0 * AVG(is_at_risk) FILTER (WHERE peer_influence = 'Negative'),
           100.0 * AVG(is_at_risk) FILTER (WHERE peer_influence = 'Positive')
    FROM base
    UNION ALL
    SELECT 'Distance_from_Home (Near vs Far)', 'School Environment',
           CORR(exam_score, -distance_enc),
           AVG(exam_score) FILTER (WHERE distance_from_home = 'Near'),
           AVG(exam_score) FILTER (WHERE distance_from_home = 'Far'),
           100.0 * AVG(is_at_risk) FILTER (WHERE distance_from_home = 'Far'),
           100.0 * AVG(is_at_risk) FILTER (WHERE distance_from_home = 'Near')
    FROM base
    UNION ALL
    SELECT 'Family_Income (High vs Low)', 'Socioeconomic & Support',
           CORR(exam_score, family_income_enc),
           AVG(exam_score) FILTER (WHERE family_income = 'High'),
           AVG(exam_score) FILTER (WHERE family_income = 'Low'),
           100.0 * AVG(is_at_risk) FILTER (WHERE family_income = 'Low'),
           100.0 * AVG(is_at_risk) FILTER (WHERE family_income = 'High')
    FROM base
    UNION ALL
    SELECT 'Motivation_Level (High vs Low)', 'Behavioral',
           CORR(exam_score, motivation_level_enc),
           AVG(exam_score) FILTER (WHERE motivation_level = 'High'),
           AVG(exam_score) FILTER (WHERE motivation_level = 'Low'),
           100.0 * AVG(is_at_risk) FILTER (WHERE motivation_level = 'Low'),
           100.0 * AVG(is_at_risk) FILTER (WHERE motivation_level = 'High')
    FROM base
    UNION ALL
    SELECT 'Teacher_Quality (High vs Low)', 'School Environment',
           CORR(exam_score, teacher_quality_enc),
           AVG(exam_score) FILTER (WHERE teacher_quality = 'High'),
           AVG(exam_score) FILTER (WHERE teacher_quality = 'Low'),
           100.0 * AVG(is_at_risk) FILTER (WHERE teacher_quality = 'Low'),
           100.0 * AVG(is_at_risk) FILTER (WHERE teacher_quality = 'High')
    FROM base
    UNION ALL
    SELECT 'Internet_Access (Yes vs No)', 'Socioeconomic & Support',
           CORR(exam_score, internet_access_enc),
           AVG(exam_score) FILTER (WHERE internet_access = 'Yes'),
           AVG(exam_score) FILTER (WHERE internet_access = 'No'),
           100.0 * AVG(is_at_risk) FILTER (WHERE internet_access = 'No'),
           100.0 * AVG(is_at_risk) FILTER (WHERE internet_access = 'Yes')
    FROM base
    UNION ALL
    SELECT 'Extracurricular_Activities (Yes vs No)', 'Behavioral',
           CORR(exam_score, extracurricular_enc),
           AVG(exam_score) FILTER (WHERE extracurricular_activities = 'Yes'),
           AVG(exam_score) FILTER (WHERE extracurricular_activities = 'No'),
           100.0 * AVG(is_at_risk) FILTER (WHERE extracurricular_activities = 'No'),
           100.0 * AVG(is_at_risk) FILTER (WHERE extracurricular_activities = 'Yes')
    FROM base
    UNION ALL
    SELECT 'Physical_Activity (Q4 vs Q1)', 'Personal & Health',
           CORR(exam_score, physical_activity),
           AVG(exam_score) FILTER (WHERE phys_q = 4),
           AVG(exam_score) FILTER (WHERE phys_q = 1),
           100.0 * AVG(is_at_risk) FILTER (WHERE phys_q = 1),
           100.0 * AVG(is_at_risk) FILTER (WHERE phys_q = 4)
    FROM base
    UNION ALL
    SELECT 'School_Type (Private vs Public)', 'School Environment',
           CORR(exam_score, private_school_enc),
           AVG(exam_score) FILTER (WHERE school_type = 'Private'),
           AVG(exam_score) FILTER (WHERE school_type = 'Public'),
           100.0 * AVG(is_at_risk) FILTER (WHERE school_type = 'Public'),
           100.0 * AVG(is_at_risk) FILTER (WHERE school_type = 'Private')
    FROM base
    UNION ALL
    SELECT 'Gender (Female vs Male)', 'Demographic',
           CORR(exam_score, female_enc),
           AVG(exam_score) FILTER (WHERE gender = 'Female'),
           AVG(exam_score) FILTER (WHERE gender = 'Male'),
           100.0 * AVG(is_at_risk) FILTER (WHERE gender = 'Male'),
           100.0 * AVG(is_at_risk) FILTER (WHERE gender = 'Female')
    FROM base
    UNION ALL
    SELECT 'Sleep_Hours (Q4 vs Q1)', 'Personal & Health',
           CORR(exam_score, sleep_hours),
           AVG(exam_score) FILTER (WHERE sleep_q = 4),
           AVG(exam_score) FILTER (WHERE sleep_q = 1),
           100.0 * AVG(is_at_risk) FILTER (WHERE sleep_q = 1),
           100.0 * AVG(is_at_risk) FILTER (WHERE sleep_q = 4)
    FROM base
)
SELECT
    RANK() OVER (ORDER BY (top_tier_mean - low_tier_mean) DESC) AS driver_rank,
    feature_name,
    domain,
    ROUND(pearson_r::NUMERIC, 3)                                AS pearson_r,
    ROUND(low_tier_mean::NUMERIC, 2)                            AS low_tier_exam,
    ROUND(top_tier_mean::NUMERIC, 2)                            AS top_tier_exam,
    ROUND((top_tier_mean - low_tier_mean)::NUMERIC, 2)          AS score_spread_pts,
    ROUND(low_tier_risk_pct::NUMERIC, 1)                        AS low_tier_risk_pct,
    ROUND(top_tier_risk_pct::NUMERIC, 1)                        AS top_tier_risk_pct
FROM feature_comparisons
ORDER BY score_spread_pts DESC;


-- ----------------------------------------------------------------------------
-- SECTION 6: 4-COHORT SEGMENTATION & TUTORING ALLOCATION SCORECARD
-- Summarizes the four student segments and exposes the tutoring mismatch:
-- tutoring sessions sit flat (~1.47-1.51/mo) across all cohorts regardless of
-- risk rate (90.4% risk in Disengaged At-Risk vs 0.7% in High-Discipline).
-- ----------------------------------------------------------------------------
SELECT
    cohort_segment,
    COUNT(*)                                                    AS students,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)          AS cohort_share_pct,
    ROUND(AVG(exam_score), 2)                                   AS avg_exam_score,
    ROUND(AVG(previous_scores), 1)                              AS avg_prior_score,
    ROUND(AVG(attendance), 1)                                   AS avg_attendance_pct,
    ROUND(AVG(hours_studied), 1)                                AS avg_hours_studied,
    ROUND(AVG(tutoring_sessions), 2)                            AS avg_tutoring_sessions,
    COUNT(*) FILTER (WHERE is_at_risk = 1)                      AS at_risk_students,
    ROUND(100.0 * AVG(is_at_risk), 1)                           AS at_risk_rate_pct
FROM vw_student_analytical_profile
GROUP BY cohort_segment
ORDER BY avg_exam_score DESC;


-- ----------------------------------------------------------------------------
-- SECTION 7: INTERACTION MATRIX — ATTENDANCE × STUDY HOURS VS PRIOR SCORE
-- Demonstrates that prior scores are virtually flat (~73.4 to 76.0) across
-- every attendance × study cell, while at-risk rate swings from 97.1% to 0.2%.
-- ----------------------------------------------------------------------------
SELECT
    CASE
        WHEN attendance < 70 THEN '1_Low (<70%)'
        WHEN attendance < 85 THEN '2_Mid (70-84%)'
        ELSE                      '3_High (85%+)'
    END                                                         AS attendance_tier,
    CASE
        WHEN hours_studied < 15  THEN '1_Low (<15h/wk)'
        WHEN hours_studied <= 24 THEN '2_Mid (15-24h/wk)'
        ELSE                          '3_High (25h+/wk)'
    END                                                         AS study_tier,
    COUNT(*)                                                    AS students,
    ROUND(AVG(previous_scores), 1)                              AS avg_prior_score,
    ROUND(AVG(exam_score), 2)                                   AS avg_exam_score,
    ROUND(100.0 * AVG(is_at_risk), 1)                           AS at_risk_rate_pct
FROM vw_student_analytical_profile
GROUP BY 1, 2
ORDER BY 1, 2;


-- ----------------------------------------------------------------------------
-- SECTION 8: ADVISING EARLY-WARNING QUEUE (vw_advising_triage_queue)
-- Operational view for academic advisors: flags students whose current
-- attendance and study hours put them at immediate risk of scoring <= 65,
-- prioritizing "Silent Slip" students (previous_scores >= 80) who are invisible
-- to legacy GPA-only warning filters and currently receive < 2 tutoring sessions.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_advising_triage_queue AS
SELECT
    student_id,
    cohort_segment,
    CASE
        WHEN previous_scores >= 80 AND attendance < 75 AND hours_studied < 18
            THEN 'P1: Silent Slip (High Prior Score, Acute Attendance/Study Drop)'
        WHEN attendance < 70 AND hours_studied < 15
            THEN 'P1: Critical Disengagement (97% Historical Risk Band)'
        WHEN access_to_resources = 'Low' AND internet_access = 'No'
            THEN 'P2: Resource & Connectivity Barrier'
        ELSE 'P3: Moderate Behavioral Drift'
    END                                                         AS triage_priority,
    previous_scores,
    attendance,
    hours_studied,
    tutoring_sessions,
    motivation_level,
    access_to_resources,
    internet_access,
    learning_disabilities,
    exam_score                                                  AS observed_exam_score,
    score_vs_income_school_peers
FROM vw_student_analytical_profile
WHERE attendance < 80
  AND hours_studied < 20
  AND tutoring_sessions < 2
    ORDER BY
    CASE
        WHEN previous_scores >= 80 AND attendance < 75 AND hours_studied < 18 THEN 1
        WHEN attendance < 70 AND hours_studied < 15 THEN 2
        ELSE 3
    END,
    attendance ASC,
    hours_studied ASC;


-- ----------------------------------------------------------------------------
-- SECTION 9: CLASSROOM & SCHOOL-OPERATIONS INTERVENTION AUDIT
-- Quantifies what happens when classroom structure and school-day supports
-- offset home resource gaps, negative peer dynamics, and learning disabilities:
--   1. In-school study hall + tutoring (hours_studied >= 20 & tutoring >= 2)
--      for low-resource or offline students cuts at-risk rate from 64.2% -> 19.3%
--   2. High teacher quality + positive peer pods cuts risk from 39.0% -> 23.5%
--   3. Targeted tutoring (>= 2/mo) + high teacher quality for students with
--      learning disabilities cuts at-risk rate from 50.9% -> 29.3%
-- ----------------------------------------------------------------------------
SELECT
    'Low Resource / No Internet' AS target_population,
    CASE
        WHEN hours_studied >= 20 AND tutoring_sessions >= 2
            THEN 'Structured Study Hall (20h+) + Tutoring (2+/mo)'
        WHEN hours_studied >= 20 AND tutoring_sessions < 2
            THEN 'Structured Study Hall (20h+) Only'
        WHEN hours_studied < 20 AND tutoring_sessions >= 2
            THEN 'Tutoring (2+/mo) Only'
        ELSE 'Baseline (Under 20h Study & <2 Tutoring)'
    END                                                         AS classroom_intervention,
    COUNT(*)                                                    AS students,
    ROUND(AVG(exam_score), 2)                                   AS avg_exam_score,
    ROUND(100.0 * AVG(is_at_risk), 1)                           AS at_risk_rate_pct
FROM vw_student_analytical_profile
WHERE access_to_resources = 'Low' OR internet_access = 'No'
GROUP BY 1, 2

UNION ALL

SELECT
    'Students with Learning Disabilities',
    CASE
        WHEN teacher_quality = 'High' AND tutoring_sessions >= 2
            THEN 'High Teacher Quality + Tutoring (2+/mo)'
        WHEN teacher_quality <> 'High' AND tutoring_sessions >= 2
            THEN 'Standard Teacher + Tutoring (2+/mo)'
        WHEN teacher_quality = 'High' AND tutoring_sessions < 2
            THEN 'High Teacher Quality Only (<2 Tutoring)'
        ELSE 'Baseline (Standard Teacher & <2 Tutoring)'
    END,
    COUNT(*),
    ROUND(AVG(exam_score), 2),
    ROUND(100.0 * AVG(is_at_risk), 1)
FROM vw_student_analytical_profile
WHERE learning_disabilities = 'Yes'
GROUP BY 1, 2
ORDER BY target_population, at_risk_rate_pct ASC;

