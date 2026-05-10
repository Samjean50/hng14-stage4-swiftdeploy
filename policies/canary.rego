package swiftdeploy.canary

import data.thresholds
import rego.v1

default allow := false

allow if {
    error_rate_ok
    latency_ok
}

error_rate_ok if {
    input.error_rate <= thresholds.max_error_rate
}

latency_ok if {
    input.p99_latency_ms <= thresholds.max_p99_latency_ms
}

reasons contains msg if {
    not error_rate_ok
    msg := sprintf(
        "Error rate %.2f%% exceeds maximum %.2f%%",
        [input.error_rate * 100, thresholds.max_error_rate * 100]
    )
}

reasons contains msg if {
    not latency_ok
    msg := sprintf(
        "P99 latency %.0fms exceeds maximum %.0fms",
        [input.p99_latency_ms, thresholds.max_p99_latency_ms]
    )
}
