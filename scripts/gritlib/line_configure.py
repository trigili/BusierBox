"""Line-console config generation helpers."""


def parse_line_config_args(args, cmd_name):
    survey_path = None
    write_config_path = None
    extra_args = []
    i = 0
    while i < len(args):
        arg = str(args[i])
        if arg in {"--write-config", "-w"} and i + 1 < len(args):
            write_config_path = str(args[i + 1])
            i += 2
        elif arg.startswith("--write-config="):
            write_config_path = arg.split("=", 1)[1]
            i += 1
        elif arg in {
            "--prefer-rshell",
            "--prefer-runtime",
            "--target-preset",
            "--payload-preset",
            "--reality-json",
        } and i + 1 < len(args):
            extra_args.extend([arg, str(args[i + 1])])
            i += 2
        elif arg in {"--allow-network-autorun", "--allow-external-writes"}:
            extra_args.append(arg)
            i += 1
        elif not arg.startswith("-"):
            survey_path = arg
            i += 1
        else:
            raise ValueError(
                f"unknown option: {arg}\n"
                f"usage: {cmd_name} [PATH] [--write-config FILE] "
                "[--prefer-rshell auto|ssh|...] [--prefer-runtime auto|...]"
            )
    return survey_path, write_config_path, extra_args
