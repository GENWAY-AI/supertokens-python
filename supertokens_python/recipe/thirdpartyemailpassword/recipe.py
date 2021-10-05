"""
Copyright (c) 2021, VRAI Labs and/or its affiliates. All rights reserved.

This software is licensed under the Apache License, Version 2.0 (the
"License") as published by the Apache Software Foundation.

You may not use this file except in compliance with the License. You may
obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
License for the specific language governing permissions and limitations
under the License.
"""
from __future__ import annotations

from os import environ
from typing import List, TYPE_CHECKING, Union

from supertokens_python.normalised_url_path import NormalisedURLPath
from supertokens_python.recipe_module import RecipeModule, APIHandled
from .api.email_password_api_impementation import get_interface_impl as get_email_password_interface_impl
from .api.implementation import APIImplementation
from .api.third_party_api_implementation import get_interface_impl as get_third_party_interface_impl
from .recipeimplementation.email_password_recipe_implementation import \
    RecipeImplementation as EmailPasswordRecipeImplementation
from .recipeimplementation.implementation import RecipeImplementation
from .recipeimplementation.third_party_recipe_implementation import \
    RecipeImplementation as ThirdPartyRecipeImplementation
from supertokens_python.framework.response import BaseResponse
from supertokens_python.querier import Querier

if TYPE_CHECKING:
    from supertokens_python.framework.request import BaseRequest
    from supertokens_python.supertokens import AppInfo
from supertokens_python.exceptions import SuperTokensError
from .exceptions import SupertokensThirdPartyEmailPasswordError
from supertokens_python.recipe.emailverification import EmailVerificationRecipe
from supertokens_python.recipe.emailpassword import EmailPasswordRecipe
from supertokens_python.recipe.thirdparty import ThirdPartyRecipe
from .utils import (
    validate_and_normalise_user_input
)


class ThirdPartyEmailPasswordRecipe(RecipeModule):
    recipe_id = 'thirdpartyemailpassword'
    __instance = None

    def __init__(self, recipe_id: str, app_info: AppInfo, config=None,
                 email_verification_recipe: Union[EmailVerificationRecipe, None] = None,
                 email_password_recipe: Union[EmailPasswordRecipe, None] = None,
                 third_party_recipe: Union[ThirdPartyRecipe, None] = None):
        super().__init__(recipe_id, app_info)
        if config is None:
            config = {}
        self.config = validate_and_normalise_user_input(self, config)

        recipe_implementation = RecipeImplementation(Querier.get_instance(EmailPasswordRecipe.recipe_id),
                                                     Querier.get_instance(ThirdPartyRecipe.recipe_id))
        self.recipe_implementation = recipe_implementation if self.config.override.functions is None else \
            self.config.override.functions(recipe_implementation)
        api_implementation = APIImplementation()
        self.api_implementation = api_implementation if self.config.override.apis is None else \
            self.config.override.apis(api_implementation)

        if email_verification_recipe is not None:
            self.email_verification_recipe = email_verification_recipe
        else:
            self.email_verification_recipe = EmailVerificationRecipe(recipe_id, app_info,
                                                                     self.config.email_verification_feature)

        def func_override_email_password(_):
            return EmailPasswordRecipeImplementation(self.recipe_implementation)

        def apis_override_email_password(_):
            return get_email_password_interface_impl(self.api_implementation)

        if email_password_recipe is not None:
            self.email_password_recipe = email_password_recipe
        else:
            self.email_password_recipe = EmailPasswordRecipe(recipe_id, app_info, {
                'sign_up_feature': {
                    'form_fields': self.config.sign_up_feature.form_fields,
                },
                'reset_password_using_token_feature': self.config.reset_password_using_token_feature,
                'email_verification_feature': {
                    'disable_default_implementation': True
                },
                'override': {
                    'functions': func_override_email_password,
                    'apis': apis_override_email_password
                }
            }, self.email_verification_recipe)

        def func_override_third_party(_):
            return ThirdPartyRecipeImplementation(self.recipe_implementation)

        def apis_override_third_party(_):
            return get_third_party_interface_impl(self.api_implementation)

        if third_party_recipe is not None:
            self.third_party_recipe = third_party_recipe
        else:
            self.third_party_recipe: Union[ThirdPartyRecipe, None] = None
            if len(self.config.providers) != 0:
                self.third_party_recipe = ThirdPartyRecipe(recipe_id, app_info, {
                    'sign_in_and_up_feature': {
                        'providers': self.config.providers
                    },
                    'override': {
                        'functions': func_override_third_party,
                        'apis': apis_override_third_party
                    }
                }, self.email_verification_recipe)

    def is_error_from_this_or_child_recipe_based_on_instance(self, err):
        return isinstance(err, SuperTokensError) and (
                isinstance(err, SupertokensThirdPartyEmailPasswordError)
                or
                self.email_verification_recipe.is_error_from_this_or_child_recipe_based_on_instance(err)
                or
                self.email_password_recipe.is_error_from_this_or_child_recipe_based_on_instance(err)
                or
                (
                        self.third_party_recipe is not None
                        and
                        self.third_party_recipe.is_error_from_this_or_child_recipe_based_on_instance(err)
                )
        )

    def get_apis_handled(self) -> List[APIHandled]:
        apis_handled = self.email_password_recipe.get_apis_handled() + self.email_verification_recipe.get_apis_handled()
        if self.third_party_recipe is not None:
            apis_handled = apis_handled + self.third_party_recipe.get_apis_handled()
        return apis_handled

    async def handle_api_request(self, request_id: str, request: BaseRequest, path: NormalisedURLPath, method: str,
                                 response: BaseResponse):
        if self.email_password_recipe.return_api_id_if_can_handle_request(path, method) is not None:
            return await self.email_password_recipe.handle_api_request(request_id, request, path, method, response)
        elif self.third_party_recipe is not None and self.third_party_recipe.return_api_id_if_can_handle_request(path,
                                                                                                                 method) is not None:
            return await self.third_party_recipe.handle_api_request(request_id, request, path, method, response)
        else:
            return await self.email_verification_recipe.handle_api_request(request_id, request, path, method, response)

    async def handle_error(self, request: BaseRequest, error: SuperTokensError, response: BaseResponse):
        if self.email_password_recipe.is_error_from_this_or_child_recipe_based_on_instance(error):
            return self.email_password_recipe.handle_error(request, error, response)
        if self.third_party_recipe is not None and self.third_party_recipe.is_error_from_this_or_child_recipe_based_on_instance(
                error):
            return self.third_party_recipe.handle_error(request, error, response)
        else:
            return self.email_verification_recipe.handle_error(request, error, response)

    def get_all_cors_headers(self) -> List[str]:
        cors_headers = self.email_password_recipe.get_all_cors_headers() + self.email_verification_recipe.get_all_cors_headers()
        if self.third_party_recipe is not None:
            cors_headers = cors_headers + self.third_party_recipe.get_all_cors_headers()
        return cors_headers

    @staticmethod
    def init(config=None):
        def func(app_info: AppInfo):
            if ThirdPartyEmailPasswordRecipe.__instance is None:
                ThirdPartyEmailPasswordRecipe.__instance = ThirdPartyEmailPasswordRecipe(
                    ThirdPartyEmailPasswordRecipe.recipe_id, app_info, config)
                return ThirdPartyEmailPasswordRecipe.__instance
            else:
                raise Exception(None, 'ThirdPartyEmailPassword recipe has already been initialised. Please '
                                              'check your code for bugs.')

        return func

    @staticmethod
    def get_instance() -> ThirdPartyEmailPasswordRecipe:
        if ThirdPartyEmailPasswordRecipe.__instance is not None:
            return ThirdPartyEmailPasswordRecipe.__instance
        raise Exception(None, 'Initialisation not done. Did you forget to call the SuperTokens.init function?')

    @staticmethod
    def reset():
        if ('SUPERTOKENS_ENV' not in environ) or (
                environ['SUPERTOKENS_ENV'] != 'testing'):
            raise Exception(None, 'calling testing function in non testing env')
        ThirdPartyRecipe.__instance = None

    async def get_email_for_user_id(self, user_id: str) -> str:
        user_info = await self.recipe_implementation.get_user_by_id(user_id)
        if user_info is None:
            raise Exception('Unknown User ID provided')
        return user_info.email
