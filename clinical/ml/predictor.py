import logging
from decimal import Decimal
from pathlib import Path
import joblib
from django.conf import settings
from clinical.models import ClinicalRiskAssessment, ClinicalRiskModelVersion, ReviewPriority
from .features import FEATURES, extract_review_features

logger = logging.getLogger(__name__)
ORDER = {'LOW':0,'MODERATE':1,'HIGH':2,'CRITICAL':3}


def resolve_artifact_path(stored_path):
    """Resolve a project-relative artifact path safely across operating systems."""
    normalized = str(stored_path).replace('\\', '/')
    artifact_path = (Path(settings.BASE_DIR) / normalized).resolve()
    artifact_path.relative_to(Path(settings.BASE_DIR).resolve())
    return artifact_path

def predict_review_priority(transaction):
    existing = ClinicalRiskAssessment.objects.filter(transaction=transaction).select_related('model_version').first()
    if transaction.status != 'DRAFT' and existing:
        return {'status':'AVAILABLE','assessment':existing}
    model_version = ClinicalRiskModelVersion.objects.filter(is_active=True).order_by('-trained_at').first()
    if not model_version:
        return {'status':'NOT_AVAILABLE','reason':'No active Decision Tree model is available.'}
    try:
        features = extract_review_features(transaction)
        if model_version.feature_schema != FEATURES:
            raise ValueError('Active model feature schema does not match runtime schema.')
        model = joblib.load(resolve_artifact_path(model_version.artifact_path))
        vector = [[features[name] for name in FEATURES]]
        raw = str(model.predict(vector)[0])
        probabilities = model.predict_proba(vector)[0]
        confidence = Decimal(str(float(probabilities[list(model.classes_).index(raw)]))).quantize(Decimal('0.000001'))
        node = 0; path = []
        tree = model.tree_
        while tree.feature[node] >= 0:
            index = tree.feature[node]; threshold = tree.threshold[node]; value = vector[0][index]
            goes_left = value <= threshold
            path.append({'feature': FEATURES[index], 'value': value, 'operator': '<=' if goes_left else '>', 'threshold': round(float(threshold), 4), 'result': bool(goes_left)})
            node = tree.children_left[node] if goes_left else tree.children_right[node]
        floor = 'CRITICAL' if features['critical_alert_count'] else ('HIGH' if features['high_alert_count'] else 'LOW')
        final = floor if ORDER[floor] > ORDER[raw] else raw
        explanation = 'The fitted Decision Tree followed structured clinical-review branches: ' + '; '.join(f"{p['feature']} {p['operator']} {p['threshold']}" for p in path) + f'. Raw result: {raw}; deterministic severity floor: {floor}; final review priority: {final}.'
        ClinicalRiskAssessment.objects.filter(transaction=transaction).delete()
        assessment = ClinicalRiskAssessment.objects.create(transaction=transaction, model_version=model_version, predicted_priority=raw, final_priority=final, prediction_probability=confidence, feature_snapshot=features, decision_path=path, explanation=explanation)
        return {'status':'AVAILABLE','assessment':assessment}
    except Exception as exc:
        logger.exception('Review-priority inference failed for transaction %s', transaction.pk)
        return {'status':'NOT_AVAILABLE','reason':str(exc)}
