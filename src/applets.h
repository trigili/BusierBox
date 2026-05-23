#ifndef BUSIERBOX_APPLETS_H
#define BUSIERBOX_APPLETS_H

struct bb_applet {
    const char *name;
    int (*main)(int argc, char **argv);
    const char *summary;
};

int bb_dispatch(const char *name, int argc, char **argv);
void bb_list_applets(int verbose);

int applet_sh_main(int argc, char **argv);
int applet_survey_main(int argc, char **argv);
int applet_envfix_main(int argc, char **argv);
int applet_list_main(int argc, char **argv);
int applet_nc_main(int argc, char **argv);
int applet_http_main(int argc, char **argv);
int applet_serve_main(int argc, char **argv);
int applet_cat_main(int argc, char **argv);
int applet_ls_main(int argc, char **argv);
int applet_hexdump_main(int argc, char **argv);
int applet_strings_main(int argc, char **argv);
int applet_sha256sum_main(int argc, char **argv);
int applet_base64_main(int argc, char **argv);
int applet_dd_main(int argc, char **argv);
int applet_uname_main(int argc, char **argv);
int applet_id_main(int argc, char **argv);
int applet_which_main(int argc, char **argv);
int applet_readlink_main(int argc, char **argv);
int applet_stat_main(int argc, char **argv);
int applet_df_main(int argc, char **argv);
int applet_free_main(int argc, char **argv);
int applet_ps_main(int argc, char **argv);
int applet_mount_main(int argc, char **argv);
int applet_env_main(int argc, char **argv);
int applet_cp_main(int argc, char **argv);
int applet_mv_main(int argc, char **argv);
int applet_rm_main(int argc, char **argv);
int applet_mkdir_main(int argc, char **argv);
int applet_chmod_main(int argc, char **argv);
int applet_touch_main(int argc, char **argv);
int applet_grep_main(int argc, char **argv);
int applet_sleep_main(int argc, char **argv);
int applet_tee_main(int argc, char **argv);

extern const struct bb_applet bb_applets[];
extern const unsigned int bb_applet_count;

#endif
