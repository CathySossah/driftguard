"""
Test de l'application des seuils de drift (sans Evidently, sans serveur) :
    python test_drift_thresholds.py
On fournit à interpret_drift_metrics une sortie au format Evidently.
"""
from app.services.drift_service import interpret_drift_metrics


def metrics(a_pvalue=0.01, b_distance=0.30):
    return [
        {"metric_name": "DriftedColumnsCount(drift_share=0.5)", "value": {"count": 2, "share": 1.0}},
        {"metric_name": "ValueDrift(column=a,method=K-S p_value,threshold=0.05)", "value": a_pvalue},
        {"metric_name": "ValueDrift(column=b,method=Wasserstein distance (normed),threshold=0.1)", "value": b_distance},
    ]


print("=== 1. Seuils par défaut ===")
r = interpret_drift_metrics(metrics())
print("  ", r["drift_score"], {k: v["drifted"] for k, v in r["columns"].items()})
assert r["columns"]["a"]["drifted"] is True       # p = 0,01 < 0,05
assert r["columns"]["b"]["drifted"] is True       # distance 0,30 >= 0,10
assert r["columns"]["a"]["kind"] == "p_value" and r["columns"]["b"]["kind"] == "distance"
assert r["drift_score"] == 1.0 and r["drift_detected"] is True

print("=== 2. Test à distance : une distance FAIBLE n'est pas une dérive (cas inversé avant correction) ===")
r = interpret_drift_metrics(metrics(b_distance=0.03))
assert r["columns"]["b"]["drifted"] is False and r["drift_score"] == 0.5

print("=== 3. Seuil de p-value global plus strict (0,001) : p = 0,01 n'est plus une dérive ===")
r = interpret_drift_metrics(metrics(), pvalue_threshold=0.001)
assert r["columns"]["a"]["drifted"] is False and r["columns"]["a"]["threshold"] == 0.001
assert r["columns"]["b"]["drifted"] is True        # le seuil global de p-value ne touche pas un test à distance
assert r["drift_score"] == 0.5

print("=== 4. Seuil personnalisé par variable ===")
r = interpret_drift_metrics(metrics(), variable_thresholds={"b": 0.5, "a": 0.2})
assert r["columns"]["b"]["drifted"] is False and r["columns"]["b"]["custom"] is True      # 0,30 < 0,5
assert r["columns"]["a"]["drifted"] is True and r["columns"]["a"]["threshold"] == 0.2     # 0,01 < 0,2
assert r["drift_score"] == 0.5
assert r["columns"]["a"]["default_threshold"] == 0.05

print("=== 5. Aucune variable en dérive ===")
r = interpret_drift_metrics(metrics(a_pvalue=0.9, b_distance=0.01))
assert r["drift_score"] == 0.0 and r["drift_detected"] is False

print("\n✅ test_drift_thresholds : OK")
