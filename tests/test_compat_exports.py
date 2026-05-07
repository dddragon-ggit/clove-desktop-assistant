from __future__ import annotations

import unittest


class CompatibilityExportTests(unittest.TestCase):
    def test_capability_compat_modules_still_export_expected_symbols(self) -> None:
        from desktop_assistant.capabilities import CapabilityRegistry as CapabilityRegistryFromCompat
        from desktop_assistant.capability import CapabilityRegistry as CapabilityRegistryFromPackage
        from desktop_assistant.capability_executor import CapabilityExecutor as CapabilityExecutorFromCompat
        from desktop_assistant.capability.executor import CapabilityExecutor as CapabilityExecutorFromPackage
        from desktop_assistant.capability_store import CapabilityStore as CapabilityStoreFromCompat
        from desktop_assistant.capability.store import CapabilityStore as CapabilityStoreFromPackage

        self.assertIs(CapabilityRegistryFromCompat, CapabilityRegistryFromPackage)
        self.assertIs(CapabilityExecutorFromCompat, CapabilityExecutorFromPackage)
        self.assertIs(CapabilityStoreFromCompat, CapabilityStoreFromPackage)

    def test_recipe_project_prompt_compat_modules_still_export_expected_symbols(self) -> None:
        from desktop_assistant.project_locator import ProjectCatalogStore as ProjectCatalogStoreFromCompat
        from desktop_assistant.projects import ProjectCatalogStore as ProjectCatalogStoreFromPackage
        from desktop_assistant.prompt_templates import PromptTemplateLibrary as PromptTemplateLibraryFromCompat
        from desktop_assistant.prompting import PromptTemplateLibrary as PromptTemplateLibraryFromPackage
        from desktop_assistant.recipes import RecipeStore as RecipeStoreFromCompat
        from desktop_assistant.recipe import RecipeStore as RecipeStoreFromPackage

        self.assertIs(ProjectCatalogStoreFromCompat, ProjectCatalogStoreFromPackage)
        self.assertIs(PromptTemplateLibraryFromCompat, PromptTemplateLibraryFromPackage)
        self.assertIs(RecipeStoreFromCompat, RecipeStoreFromPackage)


if __name__ == "__main__":
    unittest.main()
