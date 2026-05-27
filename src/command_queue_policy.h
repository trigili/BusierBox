#ifndef BUSIERBOX_COMMAND_QUEUE_POLICY_H
#define BUSIERBOX_COMMAND_QUEUE_POLICY_H

struct command_queue_policy_report {
    const char *errors[8];
    int count;
};

struct command_queue_policy_report bb_command_queue_validate_policy(void);
int bb_command_queue_policy_valid(const struct command_queue_policy_report *report);

#endif
