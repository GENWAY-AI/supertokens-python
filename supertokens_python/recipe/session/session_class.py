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
import json
from typing import Any, Dict, Union, List, TypeVar

from supertokens_python.recipe.session.exceptions import (
    raise_unauthorised_exception,
    raise_invalid_claims_exception,
    ClaimValidationError,
)

from .interfaces import SessionContainer, SessionClaimValidator, SessionClaim
from supertokens_python.logger import log_debug_message
from ...utils import resolve

_T = TypeVar("_T")


class Session(SessionContainer):
    async def revoke_session(self, user_context: Union[Any, None] = None) -> None:
        if user_context is None:
            user_context = {}
        await self.recipe_implementation.revoke_session(
            self.session_handle, user_context
        )
        self.remove_cookies = True

    async def get_session_data(
        self, user_context: Union[Dict[str, Any], None] = None
    ) -> Dict[str, Any]:
        if user_context is None:
            user_context = {}
        session_info = await self.recipe_implementation.get_session_information(
            self.session_handle, user_context
        )
        if session_info is None:
            raise_unauthorised_exception("Session does not exist anymore.")

        return session_info.session_data

    async def update_session_data(
        self,
        new_session_data: Dict[str, Any],
        user_context: Union[Dict[str, Any], None] = None,
    ) -> None:
        if user_context is None:
            user_context = {}
        updated = await self.recipe_implementation.update_session_data(
            self.session_handle, new_session_data, user_context
        )
        if not updated:
            raise_unauthorised_exception("Session does not exist anymore.")

    async def update_access_token_payload(
        self,
        new_access_token_payload: Union[Dict[str, Any], None],
        user_context: Union[Dict[str, Any], None] = None,
    ) -> None:
        if user_context is None:
            user_context = {}
        response = await self.recipe_implementation.regenerate_access_token(
            self.access_token, new_access_token_payload, user_context
        )
        if response is None:
            raise_unauthorised_exception("Session does not exist anymore.")

        self.access_token_payload = response.session.user_data_in_jwt
        if response.access_token is not None:
            self.access_token = response.access_token.token
            self.new_access_token_info = {
                "token": response.access_token.token,
                "expiry": response.access_token.expiry,
                "createdTime": response.access_token.created_time,
            }

    def get_user_id(self, user_context: Union[Dict[str, Any], None] = None) -> str:
        return self.user_id

    def get_access_token_payload(
        self, user_context: Union[Dict[str, Any], None] = None
    ) -> Dict[str, Any]:
        return self.access_token_payload

    def get_handle(self, user_context: Union[Dict[str, Any], None] = None) -> str:
        return self.session_handle

    def get_access_token(self, user_context: Union[Dict[str, Any], None] = None) -> str:
        return self.access_token

    async def get_time_created(
        self, user_context: Union[Dict[str, Any], None] = None
    ) -> int:
        if user_context is None:
            user_context = {}
        session_info = await self.recipe_implementation.get_session_information(
            self.session_handle, user_context
        )
        if session_info is None:
            raise_unauthorised_exception("Session does not exist anymore.")

        return session_info.time_created

    async def get_expiry(self, user_context: Union[Dict[str, Any], None] = None) -> int:
        if user_context is None:
            user_context = {}
        session_info = await self.recipe_implementation.get_session_information(
            self.session_handle, user_context
        )
        if session_info is None:
            raise_unauthorised_exception("Session does not exist anymore.")

        return session_info.expiry

    async def assert_claims(
        self,
        claim_validators: List[SessionClaimValidator],
        user_context: Union[Dict[str, Any], None] = None,
    ) -> None:
        original_session_claim_payload_json = json.dumps(
            self.get_access_token_payload()
        )

        new_access_token_payload = self.get_access_token_payload()
        validation_errors: List[ClaimValidationError] = []
        for validator in claim_validators:
            log_debug_message("Session.validate_claims checking %s", validator.id)
            if (
                hasattr(validator, "claim")
                and (validator.claim is not None)
                and (
                    await resolve(
                        validator.should_refetch(new_access_token_payload, user_context)
                    )
                )
            ):
                log_debug_message("Session.validate_claims refetching %s", validator.id)
                value = await resolve(
                    validator.claim.fetch_value(self.get_user_id(), user_context)
                )
                log_debug_message(
                    "Session.validate_claims %s refetch res %s",
                    validator.id,
                    json.dumps(value),
                )
                if value is not None:
                    new_access_token_payload = validator.claim.add_to_payload_(
                        new_access_token_payload,
                        value,
                        user_context,
                    )

            claim_validation_res = await resolve(
                validator.validate(new_access_token_payload, user_context)
            )
            log_debug_message(
                "Session.validate_claims %s validate res %s",
                validator.id,
                json.dumps(claim_validation_res),
            )
            if not claim_validation_res.get("isValid"):
                validation_errors.append(
                    ClaimValidationError(validator.id, claim_validation_res["reason"])
                )

        if json.dumps(new_access_token_payload) != original_session_claim_payload_json:
            await self.merge_into_access_token_payload(
                new_access_token_payload, user_context
            )

        if len(validation_errors) > 0:
            raise_invalid_claims_exception("INVALID_CLAIMS", validation_errors)

    async def fetch_and_set_claim(
        self, claim: SessionClaim[Any], user_context: Union[Dict[str, Any], None] = None
    ) -> None:
        update = await claim.build(self.get_user_id(), user_context)
        return await self.merge_into_access_token_payload(update, user_context)

    async def set_claim_value(
        self,
        claim: SessionClaim[_T],
        value: _T,
        user_context: Union[Dict[str, Any], None] = None,
    ) -> None:
        update = claim.add_to_payload_({}, value, user_context)
        return await self.merge_into_access_token_payload(update, user_context)

    async def get_claim_value(
        self, claim: SessionClaim[Any], user_context: Union[Dict[str, Any], None] = None
    ) -> Union[Any, None]:
        return claim.get_value_from_payload(
            self.get_access_token_payload(), user_context
        )

    async def remove_claim(
        self, claim: SessionClaim[Any], user_context: Union[Dict[str, Any], None] = None
    ) -> None:
        if user_context is None:
            user_context = {}
        update = claim.remove_from_payload_by_merge_({}, user_context)
        return await self.merge_into_access_token_payload(update, user_context)

    async def merge_into_access_token_payload(
        self, access_token_payload_update: Dict[str, Any], user_context: Any
    ) -> None:
        update_payload = {
            **self.get_access_token_payload(),
            **access_token_payload_update,
        }
        for k in access_token_payload_update.keys():
            if access_token_payload_update[k] is None:
                del update_payload[k]

        await self.update_access_token_payload(update_payload, user_context)
