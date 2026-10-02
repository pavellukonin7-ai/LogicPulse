def score_lead(urgency, budget, company, message):
    """Explainable triage rule; a score is not a prediction of purchase probability."""
    score, reasons = 0, []
    for points, explanation in [
        (50 if urgency == 'urgent' else 25 if urgency == 'soon' else 0,
         'Срок: в течение недели' if urgency == 'urgent' else 'Срок: в течение месяца'),
        (25 if budget is not None and budget >= 300000 else 15 if budget is not None and budget >= 100000 else 0,
         'Указанный бюджет'),
        (10 if company.strip() else 0, 'Указана компания'),
        (15 if len(message.strip()) >= 100 else 0, 'Задача описана подробно (от 100 символов)'),
    ]:
        if points:
            score += points
            reasons.append({'points': points, 'reason': explanation})
    if not reasons:
        reasons = [{'points': 0, 'reason': 'Недостаточно сигналов срочности и готовности; требуется уточнение.'}]
    return {'score': score, 'temperature': 'hot' if score >= 65 else 'warm' if score >= 35 else 'cold',
            'reasons': reasons, 'urgency': urgency, 'budget': budget, 'rule_version': '1.2.0'}
