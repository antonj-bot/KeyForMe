from app.states import ca, nj, nm

PIPELINES = {
    "CA": ca,
    "NM": nm,
    "NJ": nj,
}
# KeyForMe shared-core migration v1
from app.core.registry import extend_pipelines
PIPELINES = extend_pipelines(PIPELINES)
