-- SYNTHETIC example database dump (text-only; restored to a read-only working copy at runtime)
CREATE TABLE samples (sample_id INTEGER PRIMARY KEY, group_name TEXT, age INTEGER);
CREATE TABLE measurements (id INTEGER PRIMARY KEY, sample_id INTEGER, strength REAL);
INSERT INTO samples VALUES (1, 'A', 7), (2, 'A', 28), (3, 'B', 7), (4, 'B', 28);
INSERT INTO measurements VALUES (1, 1, 25.0), (2, 2, 34.0), (3, 3, 28.0), (4, 4, 40.0), (5, 1, 26.0);