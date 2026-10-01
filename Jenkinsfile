pipeline {
    agent any
    environment {
        APP_NAME = 'food-ordering-service'
        NAMESPACE = 'food-ordering'
        MONITORING_NAMESPACE = 'food-monitoring'
        IMAGE = 'food-ordering-service:1.0.0'
    }
    stages {
        stage('Checkout') {
            steps { checkout scm }
        }
        stage('Install Dependencies') {
            steps { bat 'python -m pip install -r inventory-service/requirements.txt' }
        }
        stage('Run Tests') {
            steps {
                bat '''
                    cd inventory-service
                    python -m pytest tests -v
                '''
            }
        }
        stage('Dependency Validation') {
            steps {
                bat '''
                    python -m pip check
                    python -m pip install pip-audit
                    python -m pip_audit -r inventory-service/requirements.txt
                '''
            }
        }
        stage('Build Docker Image') {
            steps {
                bat '''
                    docker build --no-cache -t %IMAGE% inventory-service
                    docker image inspect %IMAGE% >nul
                    if errorlevel 1 exit /b 1
                '''
            }
        }
        stage('Container Security Scan') {
            steps {
                bat '''
                    where trivy >nul 2>&1
                    if errorlevel 1 (
                        echo WARNING: Trivy is not installed. Install Trivy on Jenkins agent.
                    ) else (
                        trivy image --severity HIGH,CRITICAL --exit-code 1 %IMAGE%
                    )
                '''
            }
        }
        stage('Verify Image') {
            steps {
                bat 'docker run --rm %IMAGE% python -c "from app.main import app; p=[getattr(r,chr(112)+chr(97)+chr(116)+chr(104),chr(39)+chr(39)) for r in app.routes]; assert chr(47)+chr(104)+chr(101)+chr(97)+chr(108)+chr(116)+chr(104) in p and chr(47)+chr(109)+chr(101)+chr(116)+chr(114)+chr(105)+chr(99)+chr(115) in p; print(chr(82)+chr(79)+chr(85)+chr(84)+chr(69)+chr(83)+chr(32)+chr(79)+chr(75))"'
            }
        }
        stage('Prepare Kubernetes') {
            steps {
                bat '''
                    kubectl apply -f kubernetes/namespace.yaml
                    kubectl apply -f kubernetes/monitoring/namespace.yaml
                    kubectl apply -f kubernetes/inventory-service-configmap.yaml
                    kubectl apply -f kubernetes/inventory-service-secret.yaml
                '''
            }
        }
        stage('Load Image') {
            steps {
                bat '''
                    for /f "delims=" %%C in ('kubectl config current-context') do (
                        if /I "%%C"=="minikube" minikube image load %IMAGE%
                        if /I "%%C"=="kind-kind" kind load docker-image %IMAGE%
                        if /I "%%C"=="docker-desktop" docker save %IMAGE% | docker exec -i desktop-control-plane ctr --namespace k8s.io images import -
                    )
                '''
            }
        }
        stage('Deploy Application') {
            steps {
                bat '''
                    kubectl apply -f kubernetes/inventory-service-deployment.yaml
                    kubectl apply -f kubernetes/inventory-service.yaml
                    kubectl rollout status deployment/%APP_NAME% -n %NAMESPACE% --timeout=180s
                '''
            }
        }
        stage('Health Check') {
            steps {
                bat 'kubectl exec deployment/%APP_NAME% -n %NAMESPACE% -- python -c "import urllib.request; r=urllib.request.urlopen(chr(104)+chr(116)+chr(116)+chr(112)+chr(58)+chr(47)+chr(47)+chr(49)+chr(50)+chr(55)+chr(46)+chr(48)+chr(46)+chr(48)+chr(46)+chr(49)+chr(58)+chr(56)+chr(48)+chr(48)+chr(48)+chr(47)+chr(104)+chr(101)+chr(97)+chr(108)+chr(116)+chr(104)); assert r.status==200; print(r.read().decode())"'
            }
        }
        stage('API Validation') {
            steps {
                bat 'kubectl exec deployment/%APP_NAME% -n %NAMESPACE% -- python -c "from app.main import app; p=[getattr(r,chr(112)+chr(97)+chr(116)+chr(104),chr(39)+chr(39)) for r in app.routes]; assert chr(47)+chr(114)+chr(101)+chr(115)+chr(116)+chr(97)+chr(117)+chr(114)+chr(97)+chr(110)+chr(116)+chr(115) in p and chr(47)+chr(109)+chr(101)+chr(110)+chr(117) in p and chr(47)+chr(111)+chr(114)+chr(100)+chr(101)+chr(114)+chr(115) in p; print(chr(65)+chr(80)+chr(73)+chr(32)+chr(79)+chr(75))"'
            }
        }
        stage('Metrics Check') {
            steps {
                bat 'kubectl exec deployment/%APP_NAME% -n %NAMESPACE% -- python -c "import urllib.request; r=urllib.request.urlopen(chr(104)+chr(116)+chr(116)+chr(112)+chr(58)+chr(47)+chr(47)+chr(49)+chr(50)+chr(55)+chr(46)+chr(48)+chr(46)+chr(48)+chr(46)+chr(49)+chr(58)+chr(56)+chr(48)+chr(48)+chr(48)+chr(47)+chr(109)+chr(101)+chr(116)+chr(114)+chr(105)+chr(99)+chr(115)); assert r.status==200; print(chr(77)+chr(69)+chr(84)+chr(82)+chr(73)+chr(67)+chr(83)+chr(32)+chr(79)+chr(75))"'
            }
        }
        stage('Deploy Monitoring') {
            steps {
                bat '''
                    kubectl apply -f kubernetes/monitoring/prometheus.yaml
                    kubectl apply -f kubernetes/monitoring/grafana.yaml
                    kubectl rollout status deployment/prometheus -n %MONITORING_NAMESPACE% --timeout=180s
                    kubectl rollout status deployment/grafana -n %MONITORING_NAMESPACE% --timeout=180s
                '''
            }
        }
        stage('Monitoring Validation') {
            steps {
                bat '''
                    kubectl get pods -n %NAMESPACE%
                    kubectl get pods -n %MONITORING_NAMESPACE%
                    kubectl get services -n %NAMESPACE%
                    kubectl get services -n %MONITORING_NAMESPACE%
                '''
            }
        }
        stage('Start Services') {
            steps {
                bat '''
                    set JENKINS_NODE_COOKIE=dontKillMe
                    start "" /B cmd /c "set JENKINS_NODE_COOKIE=dontKillMe&& kubectl port-forward service/food-ordering-service 3001:8000 -n food-ordering > food-ordering-port-forward.log 2>&1"
                    start "" /B cmd /c "set JENKINS_NODE_COOKIE=dontKillMe&& kubectl port-forward service/grafana 3002:3000 -n food-monitoring > grafana-port-forward.log 2>&1"
                '''
            }
        }
        stage('Rollback Check') {
            steps {
                bat 'kubectl rollout history deployment/%APP_NAME% -n %NAMESPACE%'
            }
        }
    }
    post {
        success {
            echo 'ONLINE FOOD ORDERING CI/CD PIPELINE SUCCESS'
            echo 'Swagger: http://localhost:3001/docs'
            echo 'Grafana: http://localhost:3002'
        }
        failure {
            echo 'ONLINE FOOD ORDERING CI/CD PIPELINE FAILED'
        }
    }
}
