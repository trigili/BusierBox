"""Line REPL survey callback adapters."""


def build_line_survey_callbacks(
    cfg,
    *,
    survey_results_func,
    find_survey_uploads_func,
    survey_config_func,
    survey_preset_func,
):
    return {
        "survey_results": survey_results_func,
        "find_survey_uploads": find_survey_uploads_func,
        "survey_config": survey_config_func,
        "survey_preset": survey_preset_func,
    }
