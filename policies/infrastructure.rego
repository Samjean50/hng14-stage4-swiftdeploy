package swiftdeploy.infrastructure

import data.thresholds
import rego.v1

default allow := false

allow if {
    disk_ok
    cpu_ok
    mem_ok
}

disk_ok if {
    input.disk_free_gb >= thresholds.min_disk_free_gb
}

cpu_ok if {
    input.cpu_load <= thresholds.max_cpu_load
}

mem_ok if {
    input.mem_free_percent >= thresholds.min_mem_free_percent
}

reasons contains msg if {
    not disk_ok
    msg := sprintf(
        "Disk free %.1fGB is below minimum %.1fGB",
        [input.disk_free_gb, thresholds.min_disk_free_gb]
    )
}

reasons contains msg if {
    not cpu_ok
    msg := sprintf(
        "CPU load %.2f exceeds maximum %.2f",
        [input.cpu_load, thresholds.max_cpu_load]
    )
}

reasons contains msg if {
    not mem_ok
    msg := sprintf(
        "Memory free %.1f%% is below minimum %.1f%%",
        [input.mem_free_percent, thresholds.min_mem_free_percent]
    )
}
