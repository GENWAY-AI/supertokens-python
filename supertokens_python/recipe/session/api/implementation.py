# Copyright (c) 2021, VRAI Labs and/or its affiliates. All rights reserved.
#
# This software is licensed under the Apache License, Version 2.0 (the
# "License") as published by the Apache Software Foundation.
#
# You may not use this file except in compliance with the License. You may
# obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
from __future__ import annotations

from typing import TYPE_CHECKING, Union, List, Callable, Optional

from supertokens_python.normalised_url_path import NormalisedURLPath
from supertokens_python.recipe.session.interfaces import (
    APIInterface,
    SignOutOkayResponse,
    SessionClaimValidator,
)
from supertokens_python.types import MaybeAwaitable
from supertokens_python.utils import normalise_http_method

if TYPE_CHECKING:
    from supertokens_python.recipe.session.interfaces import APIOptions
    from ..interfaces import SessionContainer

from typing import Any, Dict

from supertokens_python.recipe.session.exceptions import UnauthorisedError


class APIImplementation(APIInterface):
    async def refresh_post(
        self, api_options: APIOptions, user_context: Dict[str, Any]
    ) -> None:
        await api_options.recipe_implementation.refresh_session(
            api_options.request, user_context
        )

    async def signout_post(
        self, api_options: APIOptions, user_context: Dict[str, Any]
    ) -> SignOutOkayResponse:
        try:
            session = await api_options.recipe_implementation.get_session(
                request=api_options.request,
                user_context=user_context,
                anti_csrf_check=None,
                session_required=True,
                override_global_claim_validators=lambda _, __, ___: [],
            )
        except UnauthorisedError:
            return SignOutOkayResponse()

        if session is None:
            raise Exception("Session is undefined. Should not come here.")
        await session.revoke_session(user_context)
        return SignOutOkayResponse()

    async def verify_session(
        self,
        api_options: APIOptions,
        anti_csrf_check: Union[bool, None],
        session_required: bool,
        override_global_claim_validators: Optional[
            Callable[
                [SessionContainer, List[SessionClaimValidator], Dict[str, Any]],
                MaybeAwaitable[List[SessionClaimValidator]],
            ]
        ],
        user_context: Dict[str, Any],
    ) -> Union[SessionContainer, None]:
        method = normalise_http_method(api_options.request.method())
        if method in ("options", "trace"):
            return None
        incoming_path = NormalisedURLPath(api_options.request.get_path())
        refresh_token_path = api_options.config.refresh_token_path
        if incoming_path.equals(refresh_token_path) and method == "post":
            return await api_options.recipe_implementation.refresh_session(
                api_options.request, user_context
            )
        session = await api_options.recipe_implementation.get_session(
            api_options.request,
            anti_csrf_check,
            session_required,
            override_global_claim_validators,
            user_context,
        )

        if session is not None:
            await api_options.recipe_implementation.assert_claims(
                session,
                override_global_claim_validators,
                user_context,
            )

        return session
