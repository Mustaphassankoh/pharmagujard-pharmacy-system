"""Offline synthetic-development trainer. Results are not clinical validation."""
import csv, json
from pathlib import Path
import joblib
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier, export_text
from django.conf import settings
from django.utils import timezone
from clinical.models import ClinicalRiskModelVersion
from .features import FEATURES

def train(dataset_path=None, version='demo-1'):
    dataset_path = Path(dataset_path or Path(__file__).parent / 'data' / 'synthetic_review_priority.csv')
    with dataset_path.open(newline='', encoding='utf-8') as handle: rows=list(csv.DictReader(handle))
    expected=set(FEATURES+['review_priority'])
    if not rows or set(rows[0]) != expected: raise ValueError('Synthetic dataset schema is invalid.')
    x=[[int(row[f]) for f in FEATURES] for row in rows]; y=[row['review_priority'] for row in rows]
    x_train,x_test,y_train,y_test=train_test_split(x,y,test_size=.25,random_state=42,stratify=y)
    model=DecisionTreeClassifier(max_depth=5,min_samples_split=4,min_samples_leaf=2,random_state=42).fit(x_train,y_train)
    predicted=model.predict(x_test); precision,recall,f1,_=precision_recall_fscore_support(y_test,predicted,average='macro',zero_division=0)
    metrics={'label':'Synthetic-development evaluation results','accuracy':accuracy_score(y_test,predicted),'precision_macro':precision,'recall_macro':recall,'f1_macro':f1,'confusion_matrix':confusion_matrix(y_test,predicted,labels=['LOW','MODERATE','HIGH','CRITICAL']).tolist()}
    artifact_dir=Path(settings.BASE_DIR)/'clinical'/'ml'/'artifacts'; artifact_dir.mkdir(parents=True,exist_ok=True)
    artifact=artifact_dir/f'decision_tree_{version}.joblib'; joblib.dump(model,artifact)
    (artifact_dir/f'decision_tree_{version}.txt').write_text(export_text(model,feature_names=FEATURES),encoding='utf-8')
    ClinicalRiskModelVersion.objects.update(is_active=False)
    record=ClinicalRiskModelVersion.objects.create(version=version,artifact_path=artifact.relative_to(settings.BASE_DIR).as_posix(),trained_at=timezone.now(),dataset_name='DEVELOPMENT / SYNTHETIC DATA — NOT CLINICALLY VALIDATED',dataset_version='1',feature_schema=FEATURES,metrics=metrics,is_active=True,notes='Prototype only; development performance does not establish clinical effectiveness.')
    return record,metrics
