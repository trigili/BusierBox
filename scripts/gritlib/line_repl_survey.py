"""Line REPL survey callback adapters."""

import gritlib.line_configure as line_configure


def build_default_line_survey_callbacks(cfg):
    return build_line_survey_callbacks(
        cfg,
        survey_results_func=line_configure.print_line_survey_status,
        find_survey_uploads_func=line_configure.find_survey_uploads,
        survey_config_func=line_configure.run_line_survey_config,
        survey_preset_func=line_configure.run_line_survey_preset,
    )


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
