import unittest

from services.thinglist_services import InventoryService, LocationService, ItemService

from site_globals import __INVENTORY__

from tests.test_parent import TestAppParent


class TestApp(TestAppParent):

    def test_delete_all_user_items(self):
        delete_all_user_items(user_id=self.users['simon'].id)


    def test_item_move(self):
        new_inventory_data = self.test_add_items()
        d = 5


    def test_relate_items(self):
        new_inventory_data, status, msg = InventoryService.add_user_list(name="test_list",
                                                        description="tet_list_desc", inventory_type=__INVENTORY__,
                                                        user_id=self.users['simon'].id)
        self.assertEqual("success", msg)
        self.assertEqual(True, status)

        _ret1 = InventoryService.add_item_to_inventory(inventory_id=new_inventory_data["id"], item_name="item1",
                                     item_desc="item1",
                                     user_id=self.users['simon'].id)

        _ret2 = InventoryService.add_item_to_inventory(inventory_id=new_inventory_data["id"], item_name="item2",
                                      item_desc="item2",
                                      user_id=self.users['simon'].id)

        status, related_items = find_related_items(item_id=_ret1["item"]["id"])
        self.assertEqual(0, len(related_items))
        self.assertEqual(True, status)

        relate_items_by_id(item1_id=_ret1["item"]["id"], item2_id=_ret2["item"]["id"])

        status, related_items = find_related_items(item_id=_ret1["item"]["id"])
        self.assertEqual(1, len(related_items))
        self.assertEqual(True, status)
        self.assertEqual(related_items[0].id, _ret2["item"]["id"])

        status, related_items = find_related_items(item_id=_ret2["item"]["id"])
        self.assertEqual(1, len(related_items))
        self.assertEqual(True, status)
        self.assertEqual(related_items[0].id, _ret1["item"]["id"])

        status, msg, unrelate_items_by_id(item1_id=_ret1["item"]["id"], item2_id=_ret2["item"]["id"])
        self.assertEqual(True, status)



    def test_add_items(self):
        _added_list_data = {}
        for _user_of_list, _list in self.new_inventory_data.items():
            new_inventory_data, status, msg = InventoryService.add_user_list(name=_list['name'],
                                                            description=_list['description'],
                                                            inventory_type=_list['list_type'],
                                                            show_default_fields=_list[
                                                                'show_default_fields'],
                                                            show_item_images=_list['show_item_images'],
                                                            show_item_type=_list['show_item_type'],
                                                            show_item_location=_list[
                                                                'show_item_location'],
                                                            show_item_tags=_list['show_item_tags'],
                                                            show_item_url=_list['show_item_url'],
                                                            access_level=_list['access_level'],
                                                            user_id=_user_of_list.id)

            if _user_of_list.id not in _added_list_data:
                _added_list_data[_user_of_list] = new_inventory_data

            _users_in_inventory = get_users_for_inventory(inventory_id=new_inventory_data["id"])
            self.assertEqual(1, len(_users_in_inventory))

            _user_default_location = LocationService.find_default_user_location(user_id=_user_of_list.id)

            for _item in self.items_to_add[_user_of_list.id]:
                _ret = InventoryService.add_item_to_inventory(inventory_id=new_inventory_data["id"], item_name=_item["name"],
                                             item_desc=_item["description"], item_type_name_or_id=_item["type"],
                                             item_specific_location=_item["specific_location"],
                                             item_tags=_item["tags"],
                                             item_quantity=_item["quantity"], item_url=_item["url"],
                                             user_id=_list['to_user_id'])

                # this should be a user item type
                _item_type = find_user_item_type_by_name(item_type_name=_item["type"],
                                                         user_id=_list['to_user_id'])
                self.assertEqual(_item_type.name, _item["type"])

                self.assertEqual("success", _ret["status"])
                _item_added = _ret["item"]
                self.assertEqual(_item["name"], _item_added["name"])
                self.assertEqual(_item["description"], _item_added["description"])

                for t in _item_added["tags"]:
                    self.assertIn(t['tag'], _item["tags"])

                self.assertEqual(_item["quantity"], _item_added["quantity"])
                self.assertEqual(_item["url"], _item_added["url"])
                self.assertEqual(_user_default_location.id, _item_added["location_id"])
                self.assertEqual(_item["specific_location"], _item_added["specific_location"])

        for _user, _new_list in _added_list_data.items():
            # no user ids passed s should return empty {}
            _items = find_items_new(inventory_id=_new_list["id"])
            self.assertEqual(0, len(_items))

            _items = find_items_new(inventory_id=_new_list["id"], logged_in_user=_user)
            self.assertEqual(2, len(_items))

            _item_type = find_user_item_type_by_name(item_type_name="printer",
                                                     user_id=_user.id)

            new_item_data = {
                "name": "test_item edited",
                "description": "test_item edited",
                "item_location": _items[0][0].location_id,
                "item_specific_location": "box 134",
                "item_type": "personal computer",
                "item_tags": ["tag11", "tag21"],
                "item_quantity": 1011,
                "item_url": "",
                # "user_id": self.users['simon'].id
            }
            ItemService.update_item_by_id(item_data=new_item_data, user=_user, item_id=_items[0][0].id)

            _item_type = find_user_item_type_by_name(item_type_name="personal computer",
                                                     user_id=_user.id)
            _query_params = {
                "item_type": _item_type.id
            }
            _items = find_items_new(inventory_id=_new_list["id"], logged_in_user=_user, query_params=_query_params)
            self.assertEqual(1, len(_items))

            self.assertEqual(_items[0][0].name, new_item_data["name"])
            self.assertEqual(_items[0][0].description, new_item_data["description"])

            # for t in new_item_data["tags"]:
            #    self.assertIn(t['tag'], _items[0][0].tags)

            self.assertEqual(_items[0][0].quantity, new_item_data["item_quantity"])
            self.assertEqual(_items[0][0].url, new_item_data["item_url"])
            self.assertEqual(_items[0][0].specific_location, new_item_data["item_specific_location"])

        return _added_list_data




    def test_delete_list(self):
        new_inventory_data = self.test_add_items()

        # pick first
        new_inventory_data = new_inventory_data[self.users['simon']]

        _user_default_list = InventoryService.get_user_default_inventory(user_id=self.users['simon'].id)
        self.assertEqual(0, len(_user_default_list.items))

        # there should be no unlisted user items
        _user_unlisted_items = get_user_unlisted_item_count(user_id=self.users['simon'].id)
        self.assertEqual(0, _user_unlisted_items)

        # if this list is deleted, the items should be reassigned to the users default list
        status, msg = delete_lists_by_id(inventory_ids=new_inventory_data["id"],
                                         user_id=self.users['simon'].id)
        self.assertEqual(True, status)

        # now there should be 2 unlisted items
        _user_unlisted_items = get_user_unlisted_item_count(user_id=self.users['simon'].id)
        self.assertEqual(2, _user_unlisted_items)

        _items = find_all_my_items(logged_in_user_id=self.users['simon'].id)
        self.assertEqual(2, len(_items))

        _item_count = get_user_item_count(user_id=self.users['simon'].id)
        self.assertEqual(2, _item_count)


if __name__ == '__main__':
    unittest.main()
