"""Re-running the wizard must not destroy credentials or keep stale ids."""
import cpd_init as I


class TestApiKeyPreservation:
    def test_blank_input_keeps_the_stored_key(self):
        assert I.api_key_to_store("", "stored-key", store_key=False) == "stored-key"

    def test_new_key_is_stored_when_asked(self):
        assert I.api_key_to_store("new-key", "stored-key", store_key=True) == "new-key"

    def test_new_key_is_dropped_when_the_user_declines_storage(self):
        assert I.api_key_to_store("new-key", "stored-key", store_key=False) == ""

    def test_blank_input_with_nothing_stored_stays_empty(self):
        assert I.api_key_to_store("", "", store_key=False) == ""


class TestResourceIdHygiene:
    def _deps(self, *ids):
        return [{"metadata": {"id": i}} for i in ids]

    def test_deployment_survives_when_the_space_still_has_it(self):
        assert I.keep_deployment("dep-1", self._deps("dep-1", "dep-2")) == "dep-1"

    def test_deployment_is_dropped_when_the_space_does_not_have_it(self):
        assert I.keep_deployment("dep-1", self._deps("dep-9")) == ""

    def test_no_previous_deployment_stays_empty(self):
        assert I.keep_deployment("", self._deps("dep-1")) == ""

    def test_ids_are_kept_for_the_same_cluster(self):
        existing = {"url": "https://a.example", "space_id": "s1", "project_id": "p1"}
        assert I.carry_over(existing, "https://a.example") == existing

    def test_a_trailing_slash_is_not_a_different_cluster(self):
        existing = {"url": "https://a.example", "space_id": "s1"}
        assert I.carry_over(existing, "https://a.example/") == existing

    def test_ids_are_dropped_when_the_cluster_changes(self):
        existing = {"url": "https://a.example", "space_id": "s1",
                    "project_id": "p1", "deployment_id": "d1",
                    "wxo_instance_url": "https://a.example/orchestrate/x"}
        kept = I.carry_over(existing, "https://b.example")
        for stale in ("space_id", "project_id", "deployment_id", "wxo_instance_url"):
            assert not kept.get(stale), f"{stale} belongs to the old cluster"
