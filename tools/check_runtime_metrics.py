"""Check an administrator's runtime-metrics JSON from stdin; no credentials."""
import argparse
import json
import math
import sys


def check(payload, max_p95_ms=2000.0, max_error_rate=.01, min_samples=20):
    runtime = payload['runtime']
    admission = payload['admission']
    count = runtime['completed_requests']
    errors = runtime['status_classes'].get('5xx', 0)
    latency = runtime['latency_ms']
    alerts = []
    if payload.get('success') is not True:
        alerts.append('metrics_response_failed')
    if type(count) is not int or count < 0 or type(errors) is not int or not 0 <= errors <= count:
        raise ValueError('Invalid request counters')
    if (type(latency['recent_sample_count']) is not int or not 0 <= latency['recent_sample_count'] <= count
            or type(latency['p95_recent']) not in (int, float) or not math.isfinite(latency['p95_recent'])
            or latency['p95_recent'] < 0):
        raise ValueError('Invalid latency samples')
    if any(type(admission[name]) is not int or admission[name] < 0
           for name in ('active', 'active_limit', 'waiting', 'queue_limit')):
        raise ValueError('Invalid admission counters')
    if count >= min_samples and errors / max(1, count) > max_error_rate:
        alerts.append('server_error_rate_since_worker_start')
    if latency['recent_sample_count'] >= min_samples and latency['p95_recent'] > max_p95_ms:
        alerts.append('recent_p95_latency')
    if (admission['active'] > admission['active_limit'] or
            admission['waiting'] > admission['queue_limit']):
        alerts.append('admission_limit_exceeded')
    if admission['queue_limit'] and admission['waiting'] >= admission['queue_limit'] * .8:
        alerts.append('request_queue_nearly_full')
    return {'healthy': not alerts, 'alerts': alerts,
            'scope': runtime['scope'], 'completed_requests': count,
            'server_error_rate_since_worker_start': round(errors / max(1, count), 5),
            'recent_p95_ms': latency['p95_recent']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-p95-ms', type=float, default=2000)
    parser.add_argument('--max-error-rate', type=float, default=.01)
    parser.add_argument('--min-samples', type=int, default=20)
    args = parser.parse_args()
    try:
        if args.max_p95_ms <= 0 or not 0 <= args.max_error_rate <= 1 or args.min_samples < 1:
            raise ValueError('Invalid thresholds')
        result = check(json.load(sys.stdin), args.max_p95_ms, args.max_error_rate, args.min_samples)
    except (ValueError, KeyError, TypeError, AttributeError):
        print(json.dumps({'healthy': False, 'error': 'Invalid runtime metrics or thresholds'}))
        return 2
    print(json.dumps(result, separators=(',', ':')))
    return 0 if result['healthy'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
