case "$-" in
    *i*)
        if [ -t 0 ] && [ -n "${SSH_TTY:-}" ] && [ -z "${GUIDO_TUI_ACTIVE:-}" ]; then
            case " $(id -nG) " in
                *" sudo "*)
                    export GUIDO_TUI_ACTIVE=1
                    sudo -n -- /usr/local/bin/guido-config
                    unset GUIDO_TUI_ACTIVE
                    ;;
                *) printf '\nGuido: TUI wymaga konta administratora.\n' ;;
            esac
        fi
        ;;
esac
