import marimo

__generated_with = "0.9.14"
app = marimo.App(width="full", app_title="Data Pipelines Sénégal")


@app.cell
def imports():
    import marimo as mo
    import pandas as pd
    import psycopg2
    import os
    from datetime import datetime, timedelta
    return mo, pd, psycopg2, os, datetime, timedelta


@app.cell
def connexion(psycopg2, os):
    def get_conn():
        return psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'postgres'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            database=os.getenv('POSTGRES_DB', 'ecommerce_senegal'),
            user=os.getenv('POSTGRES_USER', 'dataeng'),
            password=os.getenv('POSTGRES_PASSWORD', 'senegal2024'),
        )
    return (get_conn,)


@app.cell
def titre(mo):
    mo.md("""
    # Plateforme Data Pipelines — E-Commerce Sénégal
    **Stack** : Kafka · Airflow · PostgreSQL · MinIO · Marimo

    ---
    """)
    return


@app.cell
def kpis(mo, pd, get_conn):
    _conn = get_conn()

    df_kpi = pd.read_sql("""
        SELECT
            COUNT(*)                                         AS total_transactions,
            COALESCE(SUM(montant), 0)                        AS montant_total_xof,
            COALESCE(AVG(montant), 0)                        AS montant_moyen_xof,
            SUM(CASE WHEN statut = 'SUCCESS' THEN 1 ELSE 0 END) AS nb_success,
            SUM(CASE WHEN statut = 'FAILED'  THEN 1 ELSE 0 END) AS nb_echecs
        FROM paiements
        WHERE DATE(timestamp_transaction) = CURRENT_DATE
    """, _conn)

    df_anomalies_today = pd.read_sql("""
        SELECT COUNT(*) AS nb_anomalies
        FROM anomalies
        WHERE DATE(timestamp_detection) = CURRENT_DATE
    """, _conn)

    _conn.close()

    total  = int(df_kpi['total_transactions'].iloc[0])
    montant = float(df_kpi['montant_total_xof'].iloc[0])
    moyen  = float(df_kpi['montant_moyen_xof'].iloc[0])
    nb_ano = int(df_anomalies_today['nb_anomalies'].iloc[0])

    mo.hstack([
        mo.stat(label="Transactions aujourd'hui", value=f"{total:,}"),
        mo.stat(label="Montant total (XOF)",      value=f"{montant:,.0f}"),
        mo.stat(label="Montant moyen (XOF)",      value=f"{moyen:,.0f}"),
        mo.stat(label="Anomalies detectees",       value=str(nb_ano),
                caption="aujourd'hui", bordered=True),
    ])
    return


@app.cell
def repartition_methodes(mo, pd, get_conn):
    _conn = get_conn()
    df = pd.read_sql("""
        SELECT methode_paiement, COUNT(*) AS nb, COALESCE(SUM(montant), 0) AS montant
        FROM paiements
        WHERE statut = 'SUCCESS'
        GROUP BY methode_paiement
        ORDER BY nb DESC
    """, _conn)
    _conn.close()

    mo.md("## Répartition des méthodes de paiement (toutes données)")
    return (df,)


@app.cell
def table_methodes(mo, df):
    mo.ui.table(df, label="Wave vs Orange Money")
    return


@app.cell
def anomalies_recentes(mo, pd, get_conn):
    _conn = get_conn()
    df_ano = pd.read_sql("""
        SELECT
            a.transaction_id,
            a.type_anomalie,
            a.severite,
            a.montant,
            a.pays,
            a.timestamp_detection
        FROM anomalies a
        ORDER BY a.timestamp_detection DESC
        LIMIT 20
    """, _conn)
    _conn.close()

    mo.md("## 20 dernières anomalies détectées")
    return (df_ano,)


@app.cell
def table_anomalies(mo, df_ano):
    mo.ui.table(df_ano, label="Anomalies recentes")
    return


@app.cell
def stats_historique(mo, pd, get_conn):
    _conn = get_conn()
    df_stats = pd.read_sql("""
        SELECT date_stats, total_transactions, montant_total_xof,
               nb_paiements_wave, nb_paiements_orange, nb_anomalies
        FROM stats_quotidiennes
        ORDER BY date_stats DESC
        LIMIT 30
    """, _conn)
    _conn.close()

    mo.md("## Statistiques quotidiennes (30 derniers jours)")
    return (df_stats,)


@app.cell
def table_stats(mo, df_stats):
    mo.ui.table(df_stats, label="Stats quotidiennes")
    return


@app.cell
def taux_change_recent(mo, pd, get_conn):
    _conn = get_conn()
    df_taux = pd.read_sql("""
        SELECT timestamp_collecte, taux, source
        FROM taux_change
        ORDER BY timestamp_collecte DESC
        LIMIT 10
    """, _conn)
    _conn.close()

    mo.md("## Derniers taux de change XOF/USD (Source 3)")
    return (df_taux,)


@app.cell
def table_taux(mo, df_taux):
    mo.ui.table(df_taux, label="Taux de change")
    return
