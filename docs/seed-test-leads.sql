-- Equivalent fixture for this project; the lesson's SQL was not supplied.
-- Run once after 1.2 startup. Repeat is safe. No Telegram/outbox rows are inserted.
BEGIN;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM lp_services WHERE active) THEN
   RAISE EXCEPTION 'Create an active service first';
 END IF;
 IF EXISTS(SELECT 1 FROM lp_requests WHERE id LIKE '12000000-0000-4000-8000-%'
           AND consent_version <> 'test-fixture-1.2') THEN
   RAISE EXCEPTION 'Test identifier conflict';
 END IF;
END $$;
INSERT INTO lp_requests(id,service_id,service_name,name,email,company,message,consent_version,created_at,payload_hash)
SELECT '12000000-0000-4000-8000-' || lpad(n::text,12,'0'),s.id,s.name,
 'Тестовый клиент ' || lpad(n::text,2,'0'), 'demo' || n || '@example.com', 'Тест LogicPulse',
 'Тестовая заявка для проверки ранжирования LogicPulse. Требуется автоматизировать обработку обращений, интеграцию систем и отчётность. Реальным клиентом не является.',
 'test-fixture-1.2',CURRENT_TIMESTAMP,repeat('0',64)
FROM generate_series(1,10) n CROSS JOIN (SELECT id,name FROM lp_services WHERE active ORDER BY id LIMIT 1) s
ON CONFLICT(id) DO NOTHING;
INSERT INTO lp_lead_assessments(request_id,score,temperature,urgency,budget,reasons,is_test,rule_version)
SELECT '12000000-0000-4000-8000-' || lpad(n::text,12,'0'),
 CASE WHEN n<=4 THEN 100 WHEN n<=7 THEN 50 ELSE 25 END,
 CASE WHEN n<=4 THEN 'hot' WHEN n<=7 THEN 'warm' ELSE 'cold' END,
 CASE WHEN n<=4 THEN 'urgent' WHEN n<=7 THEN 'soon' ELSE 'research' END,
 CASE WHEN n<=4 THEN 300000 ELSE NULL END,
 CASE WHEN n<=4 THEN '[{"points":50,"reason":"Срок: в течение недели"},{"points":25,"reason":"Указанный бюджет"},{"points":10,"reason":"Указана компания"},{"points":15,"reason":"Задача описана подробно (от 100 символов)"}]'::json
 WHEN n<=7 THEN '[{"points":25,"reason":"Срок: в течение месяца"},{"points":10,"reason":"Указана компания"},{"points":15,"reason":"Задача описана подробно (от 100 символов)"}]'::json
 ELSE '[{"points":10,"reason":"Указана компания"},{"points":15,"reason":"Задача описана подробно (от 100 символов)"}]'::json END,
 TRUE,'1.2.0'
FROM generate_series(1,10) n ON CONFLICT(request_id) DO NOTHING;
COMMIT;
SELECT temperature,COUNT(*) FROM lp_lead_assessments WHERE is_test GROUP BY temperature;
