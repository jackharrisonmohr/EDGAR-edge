.PHONY: install lambda-package

install:
	poetry install --no-root

lambda-package: install
	# Create a directory to package the Lambda code and dependencies
	mkdir -p package

	# Install dependencies into the package directory
	poetry export --format requirements.txt --output requirements.txt --without-hashes
	pip install --target package -r requirements.txt

	# Copy the Lambda handler code into the package directory
	cp src/ingest/handler.py package/

	# Create the zip file
	cd package && zip -r9 ../lambda_ingest.zip .

	# Clean up the package directory
	rm -rf package
	rm requirements.txt
