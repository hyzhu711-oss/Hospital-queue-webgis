INSERT INTO users (id, display_name) VALUES
  (1, 'Portfolio visitor'),
  (2, 'Demo contributor A'),
  (3, 'Demo contributor B')
ON CONFLICT (id) DO UPDATE SET display_name = EXCLUDED.display_name;

SELECT setval(pg_get_serial_sequence('users', 'id'), (SELECT MAX(id) FROM users));

INSERT INTO queue_lengths (id, description, colour, sort_order) VALUES
  (1, 'Unknown', '#6b7280', 0),
  (2, 'No queue', '#2f855a', 1),
  (3, 'Under 15 minutes', '#0f766e', 2),
  (4, '15-30 minutes', '#d97706', 3),
  (5, '30-60 minutes', '#dc6b2f', 4),
  (6, 'Over 60 minutes', '#b42318', 5)
ON CONFLICT (id) DO UPDATE SET
  description = EXCLUDED.description,
  colour = EXCLUDED.colour,
  sort_order = EXCLUDED.sort_order;

SELECT setval(pg_get_serial_sequence('queue_lengths', 'id'), (SELECT MAX(id) FROM queue_lengths));

INSERT INTO hospitals (id, name, last_inspected, location, user_id) VALUES
  (1, 'Bloomsbury Community Hospital', '2026-04-14', ST_SetSRID(ST_MakePoint(-0.1347, 51.5246), 4326), 1),
  (2, 'Regent Health Centre', '2026-03-22', ST_SetSRID(ST_MakePoint(-0.1451, 51.5302), 4326), 1),
  (3, 'St Pancras Medical Centre', '2026-05-03', ST_SetSRID(ST_MakePoint(-0.1260, 51.5340), 4326), 1),
  (4, 'Camden Riverside Hospital', '2026-02-18', ST_SetSRID(ST_MakePoint(-0.1512, 51.5410), 4326), 1),
  (5, 'Fitzrovia Clinic', '2026-04-30', ST_SetSRID(ST_MakePoint(-0.1420, 51.5191), 4326), 1),
  (6, 'Holborn Health Campus', '2026-01-29', ST_SetSRID(ST_MakePoint(-0.1175, 51.5180), 4326), 1),
  (7, 'Marylebone Hospital', '2026-05-12', ST_SetSRID(ST_MakePoint(-0.1610, 51.5220), 4326), 1),
  (8, 'Islington Community Hospital', '2026-03-11', ST_SetSRID(ST_MakePoint(-0.1050, 51.5360), 4326), 1)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  last_inspected = EXCLUDED.last_inspected,
  location = EXCLUDED.location,
  user_id = EXCLUDED.user_id;

SELECT setval(pg_get_serial_sequence('hospitals', 'id'), (SELECT MAX(id) FROM hospitals));

INSERT INTO reports (id, hospital_id, user_id, queue_length_id, cleanliness, created_at) VALUES
  (1, 1, 2, 4, 'Reception was busy but the waiting area was clean.', '2026-05-18T08:30:00Z'),
  (2, 1, 1, 3, 'Clean seating area and clear signs.', '2026-05-21T10:15:00Z'),
  (3, 2, 3, 5, 'Some litter near the entrance.', '2026-05-20T13:45:00Z'),
  (4, 2, 1, 4, 'Facilities were tidy during the afternoon visit.', '2026-05-23T14:10:00Z'),
  (5, 3, 1, 2, 'Very clean and quiet.', '2026-05-24T09:05:00Z'),
  (6, 4, 2, 6, 'Crowded waiting room; surfaces appeared clean.', '2026-05-19T16:20:00Z'),
  (7, 4, 1, 5, 'Busy, but staff kept shared areas organised.', '2026-05-25T11:35:00Z'),
  (8, 5, 3, 3, 'Good overall condition.', '2026-05-22T12:25:00Z'),
  (9, 5, 1, 3, 'Clean floors and seating.', '2026-05-26T08:40:00Z'),
  (10, 6, 2, 4, 'Hand sanitiser was available.', '2026-05-24T15:50:00Z'),
  (11, 6, 1, 5, 'Waiting area needed attention near closing time.', '2026-05-27T17:15:00Z'),
  (12, 7, 3, 2, 'Bright and well maintained.', '2026-05-28T09:30:00Z'),
  (13, 1, 3, 2, 'No visible issues during the morning visit.', '2026-05-29T07:55:00Z'),
  (14, 3, 2, 3, 'Tidy entrance and reception.', '2026-05-29T12:10:00Z')
ON CONFLICT (id) DO NOTHING;

SELECT setval(pg_get_serial_sequence('reports', 'id'), (SELECT MAX(id) FROM reports));
