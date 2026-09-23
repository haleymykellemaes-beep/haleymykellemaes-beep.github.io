-- Late returns pipeline (Sakila-style public sample / WGU Advanced Data Management)
-- Clerk grain: one rental. Manager grain: store × category.
-- Not a live client.

-- Account flag → language a clerk will actually say
CREATE OR REPLACE FUNCTION fn_account_status(active_flag INT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE WHEN active_flag = 1 THEN 'Active' ELSE 'Inactive' END;
$$;

-- Null return date → Still Out; else late if past rental_date + allowed days
CREATE OR REPLACE FUNCTION fn_return_status(
    rental_ts TIMESTAMP,
    return_ts TIMESTAMP,
    allowed_days INT
)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN return_ts IS NULL THEN 'Still Out'
    WHEN return_ts > rental_ts + (allowed_days || ' days')::INTERVAL THEN 'Late'
    ELSE 'On Time'
  END;
$$;

-- Heart of the nightly extract: one row per rental after payments are summed
SELECT
    r.rental_id,
    r.rental_date,
    r.return_date,
    i.store_id,
    c.customer_id,
    (c.first_name || ' ' || c.last_name) AS customer_name,
    fn_account_status(c.active) AS customer_status,
    f.film_id,
    f.title AS film_title,
    cat.name AS category_name,
    f.rental_duration AS rental_duration_days,
    COALESCE(pay.payment_amount, 0) AS payment_amount,
    fn_return_status(
        r.rental_date::TIMESTAMP,
        r.return_date::TIMESTAMP,
        f.rental_duration
    ) AS return_status
FROM rental AS r
INNER JOIN inventory AS i      ON r.inventory_id = i.inventory_id
INNER JOIN film AS f           ON i.film_id = f.film_id
INNER JOIN film_category AS fc ON f.film_id = fc.film_id
INNER JOIN category AS cat     ON fc.category_id = cat.category_id
INNER JOIN customer AS c       ON r.customer_id = c.customer_id
LEFT JOIN (
    SELECT rental_id, SUM(amount) AS payment_amount
    FROM payment
    GROUP BY rental_id
) AS pay ON r.rental_id = pay.rental_id;

-- Manager scorecard
SELECT
    store_id,
    category_name,
    COUNT(*) AS rentals,
    SUM(payment_amount) AS revenue,
    COUNT(*) FILTER (WHERE return_status = 'On Time') AS on_time,
    COUNT(*) FILTER (WHERE return_status = 'Late') AS late,
    COUNT(*) FILTER (WHERE return_status = 'Still Out') AS still_out,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE return_status IN ('Late', 'Still Out'))
        / NULLIF(COUNT(*), 0),
        1
    ) AS late_or_out_pct
FROM detailed_rentals  -- populated by the extract + trigger in the lab
GROUP BY store_id, category_name
ORDER BY revenue DESC;
