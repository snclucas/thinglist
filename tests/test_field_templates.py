import unittest

from database_utils import get_user_template_by_id, \
    delete_templates_from_db, update_template_by_id
from services.thinglist_services import FieldTemplateService

from tests.test_parent import TestAppParent


class TestApp(TestAppParent):

    def test_add_field_template(self):
        _template_name = "test template"
        _template_field_ids = [3, 4, 5, 6, 7]
        status, msg, new_template_id = FieldTemplateService.save_template_fields(template_name=_template_name,
                                                           fields=_template_field_ids, user_id=self.users['simon'].id)
        self.assertEqual(status, True)
        self.assertEqual(msg, "success")

        user_template_ = get_user_template_by_id(template_id=new_template_id, user_id=self.users['simon'].id)
        user_template_ = user_template_[0]
        self.assertEqual(_template_name, user_template_.name)

        _returned_template_field_names = [f.field for f in user_template_.fields]
        _returned_template_field_ids = [f.id for f in user_template_.fields]

        self.assertEqual(_template_field_ids, _returned_template_field_ids)

        _user_templates = FieldTemplateService.get_user_templates(user_id=self.users['simon'].id)
        self.assertEqual(1, len(_user_templates))

        _user_template = _user_templates[0][0]
        self.assertEqual(_template_name, _user_template.name)


    def test_delete_temaplate(self):
        _template_name = "test template"
        _template_field_ids = [3, 4, 5, 6, 7]
        status, msg, new_template_id = FieldTemplateService.save_template_fields(template_name=_template_name,
                                                            fields=_template_field_ids, user_id=self.users['simon'].id)
        self.assertEqual(status, True)
        self.assertEqual(msg, "success")

        delete_templates_from_db(user_id=self.users['simon'].id, template_ids=[new_template_id])

        _user_templates = FieldTemplateService.get_user_templates(user_id=self.users['simon'].id)
        self.assertEqual(0, len(_user_templates))

    def test_update_field_template(self):
        _template_name = "test template"
        _template_field_ids = [3, 4, 5, 6, 7]
        status, msg, new_template_id = FieldTemplateService.save_template_fields(template_name=_template_name,
                                                            fields=_template_field_ids, user_id=self.users['simon'].id)
        self.assertEqual(status, True)
        self.assertEqual(msg, "success")

        user_template_ = get_user_template_by_id(template_id=new_template_id, user_id=self.users['simon'].id)
        user_template_ = user_template_[0]
        self.assertEqual(_template_name, user_template_.name)

        _returned_template_field_names = [f.field for f in user_template_.fields]
        _returned_template_field_ids = [f.id for f in user_template_.fields]

        self.assertEqual(_template_field_ids, _returned_template_field_ids)

        _new_template_field_ids = [1, 2, 3, 4]

        _new_template_data = {
            "id": new_template_id,
            "name": _template_name,
            "fields": _new_template_field_ids,
        }

        status, msg, template_id = update_template_by_id(template_data=_new_template_data, user=self.users['simon'])
        self.assertEqual(status, True)
        self.assertEqual(msg, "success")

        user_template_ = get_user_template_by_id(template_id=new_template_id, user_id=self.users['simon'].id)

        user_template_ = user_template_[0]
        self.assertEqual(_template_name, user_template_.name)

        _returned_template_field_names = [f.field for f in user_template_.fields]
        _returned_template_field_ids = [f.id for f in user_template_.fields]

        self.assertEqual(_new_template_field_ids, _returned_template_field_ids)






if __name__ == '__main__':
    unittest.main()
