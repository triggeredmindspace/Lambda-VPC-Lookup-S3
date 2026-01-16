PY=python3
PIP=${PY} -m pip

install:
	${PIP} install --upgrade pip
	${PIP} install -r requirements.txt

test:
	pytest -q

lint:
	flake8 src tests

sam-build:
	sam build --template-file infra/template.yaml

sam-deploy:
	sam deploy --template-file .aws-sam/build/template.yaml --stack-name lambda-vpc-lookup --capabilities CAPABILITY_IAM --parameter-overrides SnapshotBucket=<your-bucket>

clean:
	rm -rf .aws-sam build dist
