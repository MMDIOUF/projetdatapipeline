CREATE TABLE IF NOT EXISTS paiements (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(100) UNIQUE NOT NULL,
    montant DECIMAL(15, 2) NOT NULL,
    devise VARCHAR(3) DEFAULT 'XOF',
    methode_paiement VARCHAR(50) NOT NULL,
    numero_telephone VARCHAR(20),
    pays VARCHAR(3) DEFAULT 'SN',
    timestamp_transaction TIMESTAMP NOT NULL,
    statut VARCHAR(20) DEFAULT 'SUCCESS',
    client_id VARCHAR(100),
    produit_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_paiements_timestamp ON paiements(timestamp_transaction);
CREATE INDEX idx_paiements_methode ON paiements(methode_paiement);
CREATE INDEX idx_paiements_statut ON paiements(statut);

CREATE TABLE IF NOT EXISTS anomalies (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(100) NOT NULL,
    type_anomalie VARCHAR(100) NOT NULL,
    description TEXT,
    montant DECIMAL(15, 2),
    methode_paiement VARCHAR(50),
    pays VARCHAR(3),
    timestamp_detection TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    severite VARCHAR(20) DEFAULT 'MEDIUM',
    resolu BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_anomalies_type ON anomalies(type_anomalie);
CREATE INDEX idx_anomalies_severite ON anomalies(severite);

CREATE TABLE IF NOT EXISTS produits (
    id SERIAL PRIMARY KEY,
    produit_id VARCHAR(100) UNIQUE NOT NULL,
    nom VARCHAR(255) NOT NULL,
    categorie VARCHAR(100),
    prix_xof DECIMAL(15, 2) NOT NULL,
    prix_usd DECIMAL(15, 2),
    stock INTEGER DEFAULT 0,
    fournisseur VARCHAR(255),
    date_ajout DATE,
    date_maj TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_produits_categorie ON produits(categorie);
CREATE INDEX idx_produits_stock ON produits(stock);

CREATE TABLE IF NOT EXISTS taux_change (
    id SERIAL PRIMARY KEY,
    devise_source VARCHAR(3) DEFAULT 'XOF',
    devise_cible VARCHAR(3) DEFAULT 'USD',
    taux DECIMAL(10, 6) NOT NULL,
    timestamp_collecte TIMESTAMP NOT NULL,
    source VARCHAR(50)
);

CREATE INDEX idx_taux_timestamp ON taux_change(timestamp_collecte);

CREATE TABLE IF NOT EXISTS stats_quotidiennes (
    id SERIAL PRIMARY KEY,
    date_stats DATE UNIQUE NOT NULL,
    total_transactions INTEGER DEFAULT 0,
    montant_total_xof DECIMAL(15, 2) DEFAULT 0,
    montant_moyen_xof DECIMAL(15, 2) DEFAULT 0,
    nb_paiements_wave INTEGER DEFAULT 0,
    nb_paiements_orange INTEGER DEFAULT 0,
    nb_anomalies INTEGER DEFAULT 0,
    taux_change_moyen DECIMAL(10, 6),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE VIEW v_transactions_jour AS
SELECT
    DATE(timestamp_transaction) as date,
    methode_paiement,
    COUNT(*) as nb_transactions,
    SUM(montant) as montant_total,
    AVG(montant) as montant_moyen
FROM paiements
WHERE statut = 'SUCCESS'
GROUP BY DATE(timestamp_transaction), methode_paiement
ORDER BY date DESC;

CREATE OR REPLACE VIEW v_anomalies_actives AS
SELECT
    a.*,
    p.numero_telephone
FROM anomalies a
LEFT JOIN paiements p ON a.transaction_id = p.transaction_id
WHERE a.resolu = FALSE
ORDER BY a.timestamp_detection DESC;
