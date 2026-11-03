"""Inspect same-name records without discarding alternative credentials."""
from collections import defaultdict


def classify(records):
    groups = defaultdict(list)
    for row in records:
        groups[row['ssid']].append(row)
    labels = {}
    for group in groups.values():
        if len(group) == 1:
            continue
        same_security = defaultdict(set)
        for row in group:
            same_security[tuple(row['security_types'])].add(row['password'])
        if any(len(keys) > 1 for keys in same_security.values()):
            label = '密码冲突'
        elif len(same_security) > 1:
            label = '同名不同认证'
        else:
            equivalent = [
                {key: value for key, value in row.items() if key not in ('id', 'source')}
                for row in group
            ]
            label = '重复记录' if all(item == equivalent[0] for item in equivalent) else '同名不同配置'
        labels.update((row['id'], label) for row in group)
    return labels
