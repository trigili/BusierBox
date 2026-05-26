#ifndef BUSIERBOX_APPLETS_H
#define BUSIERBOX_APPLETS_H

#include <stddef.h>
#include <stdio.h>
#include <sys/stat.h>

struct bb_applet {
    const char *name;
    int (*main)(int argc, char **argv);
    const char *summary;
};

int bb_dispatch(const char *name, int argc, char **argv);
void bb_list_applets(int verbose);
int bb_exec_payload_applet(const char *name, int argc, char **argv);
int bb_ensure_payload_dir(char *payload, size_t payloadsz);
int bb_ensure_payload_mode(char *payload, size_t payloadsz, int require_full);
int bb_candidate_payload_dir(char *payload, size_t payloadsz);
int bb_embedded_payload_available(void);
int bb_dev_payload_archive_available(void);
int bb_payload_tool_supported(const char *name);
int bb_payload_tool_is_heavy(const char *name);
const char *bb_ledger_path(char *out, size_t outsz);
void bb_ledger_record(const char *op, const char *path, const char *scope, const char *detail);
int bb_ledger_entry_count(const char *path);
void bb_print_cleanup_ledger_json(FILE *out, void (*json_string)(FILE *, const char *));
int bb_rm_rf(const char *path);
int bb_mkdir_p(const char *path, mode_t mode);
char *bb_read_text_file(const char *path, size_t max_bytes);
int bb_read_first_line(const char *path, char *out, size_t outsz);
int bb_path_exists(const char *path);
int bb_executable_file(const char *path);
int bb_dir_is_noexec(const char *path);
unsigned long long bb_path_available_bytes(const char *path);
int bb_path_entry_count(const char *path, const char *entry);
int bb_path_has_duplicate_entries(const char *path);
int bb_choose_extract_root(char *out, size_t outsz);
unsigned long long bb_extract_required_bytes(unsigned long long payload_size);
int bb_enough_space_for_extract(unsigned long long size, const char *root);
int bb_extract_root_usable(const char *path);
void bb_print_extraction_runtime_json(FILE *out, unsigned long long payload_size,
                                      void (*json_string)(FILE *, const char *));
int bb_extract_payload_stream(FILE *fp, unsigned long long size, const char *format,
                              const char *root, int core_only);
const char *bb_ptrace_probe_status(void);
unsigned long long bb_mem_available_kb(void);
int bb_has_default_route(void);
int bb_clean_external_from_ledger(void);
void bb_set_argv0(const char *argv0);
void bb_print_applet_list(FILE *out);
int bb_print_support_token(void);
void bb_write_artifact_manifest_file(const char *root);

int applet_survey_main(int argc, char **argv);
int applet_envfix_main(int argc, char **argv);
int applet_list_main(int argc, char **argv);
int applet_extract_main(int argc, char **argv);
int applet_clean_main(int argc, char **argv);
int applet_cleanup_ledger_main(int argc, char **argv);
int applet_config_info_main(int argc, char **argv);
int applet_config_export_main(int argc, char **argv);
int applet_runtime_config_main(int argc, char **argv);
int applet_doctor_main(int argc, char **argv);
int applet_fetch_full_main(int argc, char **argv);
int applet_manifest_main(int argc, char **argv);
int applet_recovery_main(int argc, char **argv);
int applet_rshell_main(int argc, char **argv);
int applet_plan_main(int argc, char **argv);

#include "rshell_tls.h"

extern const struct bb_applet bb_applets[];
extern const unsigned int bb_applet_count;

#endif
