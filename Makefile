# Executables (local)
UV_EXEC = uv

# Misc
.DEFAULT_GOAL = help
ARGS          =
.PHONY        : help install scanner-deps run install-cli test lint lint-check release

## —— 📷 The photo-scanner Makefile 📷 ——————————————————————————
help: ## Outputs this help screen
	@grep -E '(^[a-zA-Z0-9\./_-]+:.*?##.*$$)|(^##)' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}{printf "\033[32m%-30s\033[0m %s\n", $$1, $$2}' | sed -e 's/\[32m##/[33m/'

## —— Setup 🧙 ——————————————————————————————————————————————————
install: ## Install Python deps (uv) and release tooling (npm)
	@$(UV_EXEC) sync
	@npm install

scanner-deps: ## Install SANE (scanimage) with Homebrew
	@brew install sane-backends

install-cli: ## Install the `photoscan` command globally (uv tool)
	@$(UV_EXEC) tool install --force --reinstall .

## —— App 🚀 ——————————————————————————————————————————————————
run: ## Run photoscan from the checkout, e.g. make run ARGS="session 'Grandma'"
	@$(UV_EXEC) run photoscan $(ARGS)

## —— Quality ✅ ——————————————————————————————————————————————
test: ## Run the test suite
	@$(UV_EXEC) run pytest $(ARGS)

lint: ## Fix code style with ruff
	@$(UV_EXEC) run ruff check --fix .
	@$(UV_EXEC) run ruff format .

lint-check: ## Check code style without fixing (CI-friendly)
	@$(UV_EXEC) run ruff check .
	@$(UV_EXEC) run ruff format --check .

## —— Release 📦 ——————————————————————————————————————————————
release: ## Cut a release (release-it: bump VERSION, changelog, signed tag, draft GitHub release)
	@npm run release
