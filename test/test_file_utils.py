import unittest

from cloudinary_cli.utils.file_utils import get_destination_folder


class UtilsTest(unittest.TestCase):
    def test_get_destination_folder(self):
        """ should parse option values correctly """

        self.assertEqual("1/2/3", get_destination_folder("1", "2/3/file.jpg"))
        self.assertEqual("1", get_destination_folder("1", "file.jpg"))
        self.assertEqual("cloudinaryfolder/myfolder/subfolder",
                         get_destination_folder("cloudinaryfolder",
                                                "/Users/user/myfolder/subfolder/file.jpg",
                                                parent="/Users/user/"))

