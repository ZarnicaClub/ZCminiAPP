-- Роли БД newCRM (минимальные права). Выполняется владельцем БД.
-- Пароли задаются отдельно (секреты App Platform), здесь плейсхолдеры.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'webhook_user') THEN
        CREATE ROLE webhook_user LOGIN PASSWORD 'CHANGE_ME_webhook';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'worker_user') THEN
        CREATE ROLE worker_user LOGIN PASSWORD 'CHANGE_ME_worker';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'crm_user') THEN
        CREATE ROLE crm_user LOGIN PASSWORD 'CHANGE_ME_crm';
    END IF;
END $$;

-- webhook: пишет orders, читает/пишет clients
GRANT SELECT, INSERT, UPDATE ON clients TO webhook_user;
GRANT SELECT, INSERT, UPDATE ON orders TO webhook_user;
-- БСО из Google Sheets (только дополнение существующего Order)
GRANT SELECT, INSERT, UPDATE ON orders_bso TO webhook_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO webhook_user;

-- worker: пишет calls, читает orders/clients
GRANT SELECT, INSERT, UPDATE ON clients TO worker_user;
GRANT SELECT ON orders TO worker_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON calls TO worker_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO worker_user;

-- crm: только чтение + ручной match (status/order_id у calls)
GRANT SELECT ON clients, orders, calls TO crm_user;
GRANT SELECT ON orders_bso TO crm_user;
GRANT UPDATE (status, order_id) ON calls TO crm_user;
