# Changelog

## [1.1.0](https://github.com/TomBorglum/expense-tracker/compare/v1.0.0...v1.1.0) (2026-09-03)


### Features

* return expenses and totals oldest first ([#97](https://github.com/TomBorglum/expense-tracker/issues/97)) ([6233417](https://github.com/TomBorglum/expense-tracker/commit/6233417f95b0b63b27d673c3d12c45ca9aecf53a))

## 1.0.0 (2026-09-02)


### ⚠ BREAKING CHANGES

* GET /api/greeting is gone, as is the greeting table it read from.

### Features

* add flask hello-world endpoint ([#17](https://github.com/TomBorglum/expense-tracker/issues/17)) ([3ac3037](https://github.com/TomBorglum/expense-tracker/commit/3ac303738518cd39d5dd35f965ad0caad88f7951))
* add React + Tailwind CSS v4 hello world page ([#21](https://github.com/TomBorglum/expense-tracker/issues/21)) ([66c253c](https://github.com/TomBorglum/expense-tracker/commit/66c253caddd9d41227e9710189728bdea40dd000))
* add strict type-aware eslint to the frontend ([#34](https://github.com/TomBorglum/expense-tracker/issues/34)) ([865c70e](https://github.com/TomBorglum/expense-tracker/commit/865c70e1fa84548a76f760a0c8405b35dc2d7db8))
* **backend:** aggregate expenses by period at /api/expenses/totals ([#84](https://github.com/TomBorglum/expense-tracker/issues/84)) ([1310f99](https://github.com/TomBorglum/expense-tracker/commit/1310f99c5768ddef6d5b7752d4bc0aaacb878d6f))
* **backend:** load expenses from a directory outside the repository ([#94](https://github.com/TomBorglum/expense-tracker/issues/94)) ([f96defc](https://github.com/TomBorglum/expense-tracker/commit/f96defc154314bf1dae385179bd5a4872277c6e0))
* **backend:** load expenses from TSV files and serve them over the API ([#50](https://github.com/TomBorglum/expense-tracker/issues/50)) ([472fd9b](https://github.com/TomBorglum/expense-tracker/commit/472fd9bd75bba1d7f0427006aa4869d27866fd9c))
* **backend:** select a range of dates on /api/expenses ([#73](https://github.com/TomBorglum/expense-tracker/issues/73)) ([ac23d91](https://github.com/TomBorglum/expense-tracker/commit/ac23d911e51551345644cc29c307070d56c46ee6))
* **backend:** serve currency exchange rates at /api/currencies ([#69](https://github.com/TomBorglum/expense-tracker/issues/69)) ([2fd66c8](https://github.com/TomBorglum/expense-tracker/commit/2fd66c8cc03350bc02e2ad5ef0eb3d2a3f68e0c0))
* **backend:** serve the greeting from postgres ([#43](https://github.com/TomBorglum/expense-tracker/issues/43)) ([030306e](https://github.com/TomBorglum/expense-tracker/commit/030306ede3900629b22b34c051930b1515c4b95b))
* **backend:** show expenses in a requested currency ([#70](https://github.com/TomBorglum/expense-tracker/issues/70)) ([1147c04](https://github.com/TomBorglum/expense-tracker/commit/1147c0438c8bd9135a671c5ab5cde5725cc0ba64))
* **backend:** start the database from backend-dev ([#61](https://github.com/TomBorglum/expense-tracker/issues/61)) ([0528f4e](https://github.com/TomBorglum/expense-tracker/commit/0528f4ef5aa00e31249b84843d871e685921d60f))
* **backend:** start the database from backend-dev ([#62](https://github.com/TomBorglum/expense-tracker/issues/62)) ([03d138f](https://github.com/TomBorglum/expense-tracker/commit/03d138f41d8c953375fe427bc08d8dc8f967be24))
* **backend:** take the dev API port from backend/.env ([#63](https://github.com/TomBorglum/expense-tracker/issues/63)) ([ab04a50](https://github.com/TomBorglum/expense-tracker/commit/ab04a50c5cb6804c0e7152226764bd157ec3f4df))
* **frontend:** add an expenses page ([#54](https://github.com/TomBorglum/expense-tracker/issues/54)) ([79efd8b](https://github.com/TomBorglum/expense-tracker/commit/79efd8bacae74800e01a0315d549d01f9ea36adc))
* **frontend:** carry the currency and the date range between the two views ([#90](https://github.com/TomBorglum/expense-tracker/issues/90)) ([3087784](https://github.com/TomBorglum/expense-tracker/commit/30877846b067478ef0b678435eb8b0373246d0fb))
* **frontend:** filter the expenses by a date range ([#74](https://github.com/TomBorglum/expense-tracker/issues/74)) ([4bcc9d7](https://github.com/TomBorglum/expense-tracker/commit/4bcc9d749c1c82d8420231cbe2783962729f7bb3))
* **frontend:** give the category breakdown a column of its own ([#92](https://github.com/TomBorglum/expense-tracker/issues/92)) ([435831d](https://github.com/TomBorglum/expense-tracker/commit/435831d688156a8eb60576e694dc28cba0dc854b))
* **frontend:** head the totals table with its column names ([#91](https://github.com/TomBorglum/expense-tracker/issues/91)) ([6da698f](https://github.com/TomBorglum/expense-tracker/commit/6da698fa92f571ae191a5975a981b3952933cc72))
* **frontend:** keep the expenses table headers in view while the rows scroll ([#89](https://github.com/TomBorglum/expense-tracker/issues/89)) ([6a9e896](https://github.com/TomBorglum/expense-tracker/commit/6a9e8961073f45bf730550d5b5d7bee41db88574))
* **frontend:** let the expenses be shown in a chosen currency ([#71](https://github.com/TomBorglum/expense-tracker/issues/71)) ([4e5e227](https://github.com/TomBorglum/expense-tracker/commit/4e5e227bc6fb4ff1d6694aa1d6f50d0e3be16c3c))
* **frontend:** order the expenses columns like the totals columns ([#93](https://github.com/TomBorglum/expense-tracker/issues/93)) ([481ec75](https://github.com/TomBorglum/expense-tracker/commit/481ec753653135a8c9f48e8b0ec7936b3aa5eeba))
* **frontend:** present the period totals at /totals ([#86](https://github.com/TomBorglum/expense-tracker/issues/86)) ([0fc0868](https://github.com/TomBorglum/expense-tracker/commit/0fc0868a57f12ef3cca3bdfefde7906fe2de4600))
* **frontend:** style the app with a single dark daisyUI theme ([#67](https://github.com/TomBorglum/expense-tracker/issues/67)) ([b1dcc3b](https://github.com/TomBorglum/expense-tracker/commit/b1dcc3b66aafeb4068327e11971f94cc3b0cdcc5))
* remove the greeting endpoint ([#66](https://github.com/TomBorglum/expense-tracker/issues/66)) ([2811cf4](https://github.com/TomBorglum/expense-tracker/commit/2811cf4f3014e5ca676cc2fb35c0287bafac9db9))
* serve the greeting from a JSON API ([#33](https://github.com/TomBorglum/expense-tracker/issues/33)) ([1573add](https://github.com/TomBorglum/expense-tracker/commit/1573add11836d56dd876489b8d164a6b206c39ea))


### Bug Fixes

* **backend:** show the server log when db-start fails ([#65](https://github.com/TomBorglum/expense-tracker/issues/65)) ([0002917](https://github.com/TomBorglum/expense-tracker/commit/000291798b28977180080bdd11a941489539443a))
* **frontend:** bring the calendar onto the page's type scale ([#83](https://github.com/TomBorglum/expense-tracker/issues/83)) ([8123a5a](https://github.com/TomBorglum/expense-tracker/commit/8123a5a733e4349551bc28f6bdfb2d13db24a4ca))
* **frontend:** make the filter controls and type scale consistent ([#78](https://github.com/TomBorglum/expense-tracker/issues/78)) ([f26600b](https://github.com/TomBorglum/expense-tracker/commit/f26600bfe4e4bdc4769492a7bb39a534417ed0c1))
* **frontend:** say the same thing in both views when a range holds no expenses ([#95](https://github.com/TomBorglum/expense-tracker/issues/95)) ([94977bd](https://github.com/TomBorglum/expense-tracker/commit/94977bded39ded8e89e92366d4c2ee41fc9ce216))
* give basedpyright the config file path, not its directory ([#39](https://github.com/TomBorglum/expense-tracker/issues/39)) ([4ed7dda](https://github.com/TomBorglum/expense-tracker/commit/4ed7dda1ccb4a18acbc1d9566e8923d74e0a9b63))
* point Zed's basedpyright at backend/pyproject.toml ([#38](https://github.com/TomBorglum/expense-tracker/issues/38)) ([74ddc38](https://github.com/TomBorglum/expense-tracker/commit/74ddc38a822393d797f36c98f75f404e046ecb6b))


### Dependencies

* Bump daisyui in /frontend in the frontend group ([#81](https://github.com/TomBorglum/expense-tracker/issues/81)) ([452c243](https://github.com/TomBorglum/expense-tracker/commit/452c24318e9d64a842f6bb17c78d4bfc80cac77a))
* bump python to 3.14.7 ([#82](https://github.com/TomBorglum/expense-tracker/issues/82)) ([a7ed2cd](https://github.com/TomBorglum/expense-tracker/commit/a7ed2cd1e8d96d890f30652f947f90859ed8bf24))
* bump the frontend group in /frontend with 6 updates ([#88](https://github.com/TomBorglum/expense-tracker/issues/88)) ([a1c2e16](https://github.com/TomBorglum/expense-tracker/commit/a1c2e164ddd8411edaacd4180a14ab1b72553f8f))
