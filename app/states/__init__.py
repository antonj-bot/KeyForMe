from app.states import ca, nm

PIPELINES = {
    "CA": ca,
    "NM": nm,
}
# KeyForMe shared-core migration v1
from app.core.registry import extend_pipelines
PIPELINES = extend_pipelines(PIPELINES)
