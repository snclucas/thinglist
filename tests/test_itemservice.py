# python
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import app
import routes.item_routes as item_routes


class TestItemRoutes(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

        # Create a mock current_user and patch it into the module
        self.mock_user = SimpleNamespace(is_authenticated=True, id=1, username='simon')
        self.patcher_current_user = patch.object(item_routes, 'current_user', self.mock_user)
        self.patcher_current_user.start()

        # Patch constants for predictable behavior (if needed)
        # Patch site globals are imported in module already, so not required here.

        # Common simple objects returned by services
        self.mock_item = SimpleNamespace(id=123, location_id=10, slug='new-slug', name='Test Item')
        self.mock_itemtype = 'SomeType'
        self.mock_inventory_item = SimpleNamespace(id=999)

        # Start generic service patches; tests will adjust return values per test
        self.patcher_ItemService = patch.object(item_routes, 'ItemService', autospec=True)
        self.mock_ItemService = self.patcher_ItemService.start()

        self.patcher_FieldService = patch.object(item_routes, 'FieldService', autospec=True)
        self.mock_FieldService = self.patcher_FieldService.start()

        self.patcher_LocationService = patch.object(item_routes, 'LocationService', autospec=True)
        self.mock_LocationService = self.patcher_LocationService.start()

        self.patcher_UserService = patch.object(item_routes, 'UserService', autospec=True)
        self.mock_UserService = self.patcher_UserService.start()

        self.patcher_InventoryService = patch.object(item_routes, 'InventoryService', autospec=True)
        self.mock_InventoryService = self.patcher_InventoryService.start()

        self.patcher_ItemTypeService = patch.object(item_routes, 'ItemTypeService', autospec=True)
        self.mock_ItemTypeService = self.patcher_ItemTypeService.start()

        self.patcher_ImageService = patch.object(item_routes, 'ImageService', autospec=True)
        self.mock_ImageService = self.patcher_ImageService.start()

        self.patcher_FieldTemplateService = patch.object(item_routes, 'FieldTemplateService', autospec=True)
        self.mock_FieldTemplateService = self.patcher_FieldTemplateService.start()

        # Patch filesystem write to avoid disk writes
        self.patcher_write_bytes = patch('pathlib.Path.write_bytes', return_value=None)
        self.patcher_write_bytes.start()

        # Patch image helpers and filename generator used in upload
        self.patcher_generate_filename = patch.object(item_routes, 'generate_item_image_filename', return_value='img1.jpg')
        self.patcher_generate_filename.start()

        # Patch PIL Image.open to return a simple image-like object with required methods
        class FakeImage:
            def convert(self, mode): return self
            def thumbnail(self, size): return None
            def save(self, fobj, format=None): fobj.write(b'JPEGDATA')
        self.patcher_ImageOpen = patch.object(item_routes, 'Image', Mock(open=Mock(return_value=FakeImage()), new=Mock()))
        self.patcher_ImageOpen.start()

        # Patch orientation helper to no-op
        self.patcher_correct_orientation = patch.object(item_routes, 'correct_image_orientation', lambda image: image)
        self.patcher_correct_orientation.start()

    def tearDown(self):
        patch.stopall()

    def test_item_view_returns_200_for_public_inventory(self):
        # Setup services for viewing a public item
        self.mock_UserService.get_user_by_username.return_value = SimpleNamespace(id=42, username='simon')
        # InventoryService returns (inventory_obj, user_inventory) where inventory exists and public
        inventory_obj = SimpleNamespace(id=11, access_level=item_routes.__PUBLIC__)
        self.mock_InventoryService.find_inventory_by_slug.return_value = (inventory_obj, None)
        # ItemService returns (item, itemtype, inventory_item)
        self.mock_ItemService.get_item_by_slug.return_value = (self.mock_item, self.mock_itemtype, self.mock_inventory_item)
        # ItemService fields
        self.mock_ItemService.get_item_fields.return_value = [(SimpleNamespace(field='f1'), SimpleNamespace(value='v1'), SimpleNamespace(order=1))]
        self.mock_ItemService.get_all_item_fields.return_value = {}
        self.mock_FieldService.get_all_fields.return_value = []
        self.mock_ItemTypeService.get_all_user_and_system_item_types.return_value = []

        resp = self.client.get('/@simon/d/test-item')
        self.assertEqual(resp.status_code, 200)
        # Ensure ItemService was queried
        self.mock_ItemService.get_item_by_slug.assert_called_once_with(item_slug='test-item', user_id=None)

    def test_edit_item_success_redirects_and_updates_fields(self):
        # Prepare form data (multipart not required)
        form = {
            'csrf_token': 'x',
            'item_slug': 'old-slug',
            'inventory_slug': 'inv-slug',
            'list_username': 'simon',
            'item_name': 'New name',
            'item_description': 'desc',
            'item_quantity': '2',
            'item_url': 'http://example.com',
            'item_tags': '',
            'item_type': 't',
            'item_location': 'l',
            'item_specific_location': 'sl',
            # dynamic field inputs:
            '1': 'val1',
            '2': 'val2',
        }

        # ItemService.update_item_by_id returns success and new slug
        self.mock_ItemService.update_item_by_id.return_value = {"status": "success", "item": {"slug": "new-slug"}}
        # update_item_fields no-op
        self.mock_ItemService.update_item_fields.return_value = None

        resp = self.client.post('/item/edit/123', data=form, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        # redirect should contain the new slug
        self.assertIn('new-slug', resp.headers['Location'])
        self.mock_ItemService.update_item_by_id.assert_called_once()

    def test_edit_item_description_too_long_flashes_and_redirects(self):
        long_desc = 'x' * (int(app.config.get('ITEM_DESCRIPTION_CHAR_LIMIT', 10)) + 50)
        form = {
            'csrf_token': 'x',
            'item_slug': 'old-slug',
            'inventory_slug': 'inv-slug',
            'list_username': 'simon',
            'item_name': 'Name',
            'item_description': long_desc,
            'item_quantity': '1',
            'item_url': '',
            'item_tags': '',
            'item_type': '',
            'item_location': '',
            'item_specific_location': '',
        }
        resp = self.client.post('/item/edit/123', data=form, follow_redirects=False)
        # description too long causes redirect back to item view
        self.assertEqual(resp.status_code, 302)

    def test_edit_item_fields_sets_visibility(self):
        payload = {"item_id": 123, "field_ids": [1, 2, 3]}
        resp = self.client.post('/item/fields', json=payload)
        self.assertEqual(resp.status_code, 200)
        # Since the view returns True as Python bool, the body contains "True"
        self.assertIn(b'True', resp.data)
        self.mock_FieldService.set_field_status.assert_called_once_with(123, [1, 2, 3], is_visible=True)

    def test_edit_inventory_default_fields_calls_service(self):
        payload = {"inventory_id": 10, "field_ids": [1, 2]}
        resp = self.client.post('/default-inventory_fields', json=payload)
        self.assertEqual(resp.status_code, 200)
        self.mock_InventoryService.set_inventory_default_fields.assert_called_once()

    def test_save_inventory_template_redirects(self):
        form = {"inventory_id": "10", "inventory_slug": "inv-slug", "inventory_template": "5"}
        self.mock_FieldTemplateService.save_inventory_fieldtemplate.return_value = True
        resp = self.client.post('/inventory/save-inventory-template', data=form, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        # redirect to the items listing for current user
        self.assertIn(self.mock_user.username, resp.headers['Location'])

    def test_relate_items_success(self):
        # prepare form with related item slug that exists
        form = {
            'item_id': '123',
            'relateditem': 'other-slug',
            'inventory_slug': 'inv',
            'item_slug': 'item-slug'
        }
        # make ItemService.get_item_by_slug return a different item id
        related_item = SimpleNamespace(id=999)
        self.mock_ItemService.get_item_by_slug.return_value = (related_item, self.mock_itemtype, self.mock_inventory_item)
        resp = self.client.post('/item/relate-items', data=form, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.mock_ItemService.relate_items_by_id.assert_called_once()

    def test_unrelate_items_requires_auth_and_returns_json(self):
        payload = {"item1": 1, "item2": 2}
        # current_user.is_authenticated is True in setUp
        self.mock_ItemService.unrelate_items_by_id.return_value = (True, "ok")
        resp = self.client.post('/unrelate-items', json=payload)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data.decode())
        self.assertTrue(data.get('success'))

    def test_delete_images_redirects_and_calls_image_service(self):
        payload = {
            "item_id": 123,
            "item_slug": "item-slug",
            "inventory_slug": "inv-slug",
            "username": "simon",
            "image_id_list": ["img1", "img2"]
        }
        self.mock_ImageService.delete_images_from_item.return_value = (True, "ok")
        resp = self.client.post('/item/images/remove', json=payload, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.mock_ImageService.delete_images_from_item.assert_called_once()

    def test_set_main_image_requires_fields_and_sets_image(self):
        # missing fields -> 400
        resp = self.client.post('/item/images/setmainimage', json={})
        self.assertEqual(resp.status_code, 400)
        # valid payload triggers ImageService.set_item_main_image and redirect
        payload = {
            "main_image": "/uploads/path/img.jpg",
            "item_slug": "item-slug",
            "inventory_slug": "inv-slug",
            "item_id": 123,
            "username": "simon"
        }
        resp = self.client.post('/item/images/setmainimage', json=payload, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.mock_ImageService.set_item_main_image.assert_called_once()

    def test_upload_image_flow_saves_and_adds_to_item(self):
        # prepare a small binary that looks like an image file
        img_bytes = b'\xFF\xD8\xFF\xD9'  # minimal JPEG markers
        data = {
            'username': self.mock_user.username,
            'item_id': '123',
            'item_slug': 'item-slug',
            'inventory_slug': 'inv-slug',
            'file[]': (io.BytesIO(img_bytes), 'test.jpg')
        }
        # call upload endpoint
        resp = self.client.post('/item/images/upload', data=data, content_type='multipart/form-data', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        # ensure add_images_to_item was called (patch object used)
        self.mock_ImageService.add_images_to_item.assert_called_once()

    def test_item_view_returns_404_when_item_missing(self):
        # set InventoryService to return a valid inventory
        self.mock_UserService.get_user_by_username.return_value = SimpleNamespace(id=42, username='simon')
        inventory_obj = SimpleNamespace(id=11, access_level=item_routes.__PUBLIC__)
        self.mock_InventoryService.find_inventory_by_slug.return_value = (inventory_obj, None)
        # ItemService returns None to indicate missing item
        self.mock_ItemService.get_item_by_slug.return_value = None
        resp = self.client.get('/@simon/d/does-not-exist')
        self.assertEqual(resp.status_code, 404)


if __name__ == '__main__':
    unittest.main()
