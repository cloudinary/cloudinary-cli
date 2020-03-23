import click
import cloudinary
from click import command, option
from cloudinary_cli.defaults import logger
from cloudinary import api


@command("find_empty_folders", help="Find empty folders in your cloud.")
@option("-D", "--delete", is_flag=True, help="Delete the empty folders")
def find_empty_folders(delete):
    def find_end(root, f):
        response = list(
            filter(lambda x: x != 'search', list(map(lambda x: x['path'], api.subfolders(root)['folders']))))
        _ = [find_end(i, f) for i in response] if response != [] else f.append(root)
        if root == "":
            return f

    logger.info("Finding empty folders...")

    empty = list(
        filter(lambda x: cloudinary.Search().expression("folder=\"{}\"".format(x)).execute()['total_count'] == 0,
               find_end("", [])))

    logger.info("Empty folders:\n{}".format(empty))

    if delete:
        logger.info("\nDeleting empty folders...")
        for f in empty:
            try:
                res = api.delete_folder(f)
                logger.info("Deleted folder \"{}.\"".format(f))
            except Exception as e:
                logger.error("Folder \"{}\" is not empty. It may have a placeholder or backed up asset.".format(f))
                pass
