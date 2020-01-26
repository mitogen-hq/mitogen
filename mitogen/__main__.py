import click
import ansible_mitogen
import os
import sys


@click.pass_context
def all_procedure(ctx, dry_run, prepare):
    if (dry_run is False) and (prepare is False):
        print_help(ctx, None, value=True)

@click.command()
@click.version_option()
@click.option("--path", "-p", is_flag=True, default=False, help="Return path to add to Ansible")
@click.pass_context
def main(ctx, path):

    if not path:
        click.echo(ctx.get_help())
    else:
        p = os.path.abspath(
            os.path.join(
            os.path.dirname(ansible_mitogen.__file__),
            "plugins", "strategy"))

        print(p)

if __name__ == "__main__":

    main()
