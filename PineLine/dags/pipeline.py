import uuid
import pymongo
import datetime as dt
import json
import random

# from midtermDAG import DAG
# from midtermOperator import BashOperator
# from midtermOperator import PythonOperator
from airflow import DAG
from airflow.operators.bash_operator import BashOperator    
from airflow.operators.python_operator import PythonOperator

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

# Hoàn thành việc kết nối với MongoDB và Qdrant
qdrant_client = QdrantClient(host="qdrant_db", port=6333)
mongo_client = pymongo.MongoClient("mongodb://admin:admin@mongo_db:27017")
database_mongo = mongo_client["midterm"]
# tạo collection có tên là mssv của bạn trong MongoDB và Qdrant
# ví dụ mssv của bạn là 17101691 thi tên collection sẽ là "17101691"
collection_mongo = database_mongo["12345678"]
name_collection_qdrant = '12345678'


def create_collection_qdrant():
    try:
        # lấy tên tất cả collection hiện có trong Qdrant
        cles = qdrant_client.get_collections()
        names = [c.name for c in cles.collections]

        # cấu hình vector params cho collection bao gồm size = 1536 và distance = cosine
        vectorParams = {
            'size': 1536,
            'distance': Distance.COSINE
        }
        ### YOUR CODE HERE ###
        # kiểm tra nếu collection chưa tồn tại thì tạo mới
        # Sử dụng **vectorParams để unpack dict thành các keyword arguments
        if name_collection_qdrant not in names:
            qdrant_client.recreate_collection(
                collection_name=name_collection_qdrant,
                vectors_config=VectorParams(**vectorParams)
            )
            return {
                "status": "success",
                "collection": name_collection_qdrant,
                "vectorParams": str(vectorParams)
            }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def insert_data_mongoDB():
    try:
        # đọc dữ liệu từ file data_iuh_new.json và chọn ngẫu nhiên điểm dữ liệu gán vào biến data
        json_data = None
        with open("/opt/airflow/dags/data_iuh_new.json", "r") as f:
            json_data = json.load(f)
        message = ""
        data = json_data[random.randint(1, len(json_data))]
        # kiểm tra title của điểm dữ liệu đã tồn tại trong MongoDB chưa
        # nếu đã tồn tại thì gán "Data already exists" cho biến message
        # nếu chưa thì thêm trường "status": "new" vào data và insert vào MongoDB 
        # sau đó gán "Data inserted" cho biến message
        check = collection_mongo.find({'title': data['title']})
        dup = 0
        for _ in check:
            dup = 1

        if dup == 1:
            message = "Data already exists"
        else:
            data["status"] = "new"
            _ = collection_mongo.insert_one(data)
            message = "Data inserted"

        title = data["title"]
        return {
            "status": "success",
            "data": title,
            "message": message
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def insert_data_qdrant():
    try:
        # lấy tất cả các điểm dữ liệu có "status":"new" từ MongoDB
        # insert các điểm dữ liệu này vào Qdrant (lưu ý: không insert trường "_id" và "embedding" của MongoDB vào Qdrant)
        # sau khi insert thành công thì cập nhật trường "status":"indexed" cho các điểm dữ liệu đã insert trong MongoDB
        # Lấy tất cả các bản ghi có "status":"new" từ MongoDB
        new_records = collection_mongo.find({"status": "new"})

        for new in new_records:
            id = new.pop('_id')
            vector = new['embedding']
            _ = new.pop('embedding')
            point = PointStruct(id=str(uuid.uuid4()),
                                vector=vector,
                                payload=new)
            qdrant_client.upsert(collection_name=name_collection_qdrant, points=[point])
            collection_mongo.update_one({"_id": id}, {"$set": {"status": "indexed"}})

        return {
            "status": "success",
            "message": "Data inserted to Vector DB successfully"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def count_data():
    try:
        count = collection_mongo.count_documents({})
        count_indexed = collection_mongo.count_documents({"status": "indexed"})
        count_new = collection_mongo.count_documents({"status": "new"})
        return {
            "status": "success",
            "indexed": count_indexed,
            "new": count_new,
            "mongoDB": count,
            "vectorDB": qdrant_client.get_collection(collection_name=name_collection_qdrant).points_count
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def search_by_vector():
    try:
        # tạo ngẫu nhiên một vector có size = 1536 và sử dụng Qdrant để tìm kiếm 1 điểm gần nhất
        vector = [random.random() for i in range(1536)]
        # tìm kiếm 1 điểm gần nhất
        result = qdrant_client.search(collection_name=name_collection_qdrant, query_vector=vector, limit=1)

        result_json = result[0].model_dump()
        return {
            "status": "success",
            "result": str(result_json)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

# đặt owner là mssv của bạn, Thử lại 1 lần nếu thất bại, thời gian chờ giữa các lần thử là 1 phút
default_args = {
    'owner': '12345678',
    'start_date': dt.datetime.now() - dt.timedelta(minutes=2),
    'retries': 1,
    'retry_delay': dt.timedelta(minutes=2),
}


# khởi tạo DAG với tên là mssv của bạn và cài đặt mỗi 5 phút chạy 1 lần

with DAG('12345678', 
         default_args=default_args,
         tags=['midterm'],
         schedule_interval=dt.timedelta(minutes=5),
         ) as dag:
    t1 = BashOperator(task_id='start', bash_command='echo "Midterm exam started"')
    t2 = PythonOperator(task_id='init_qdrant', python_callable=create_collection_qdrant)
    t3 = PythonOperator(task_id='insert_mongo', python_callable=insert_data_mongoDB)
    t4 = PythonOperator(task_id='insert_qdrant', python_callable=insert_data_qdrant)
    t5 = PythonOperator(task_id='count', python_callable=count_data)
    t6 = PythonOperator(task_id='search', python_callable=search_by_vector)
    t7 = BashOperator(task_id='end', bash_command='echo "Midterm exam ended"')
    # khởi tạo pipeline sử dụng BashOperator và PythonOperator như sau:
    # task 1: sử dụng BashOperator để in ra "Midterm exam started" với task_id là mssv của bạn (ví dụ: task_id='17101691')
    # task 2: sử dụng PythonOperator để tạo collection trong Qdrant với task_id là 4 chữ số đầu của mssv của bạn (ví dụ: task_id='1710')
    # task 3: sử dụng PythonOperator để insert data vào MongoDB với task_id là 3 chữ số cuối của task2 và số kế tiếp trong mssv (ví dụ: task_id='7101')
    # task 4: sử dụng PythonOperator để insert data vào Qdrant với task_id là 3 chữ số cuối của task3 và số kế tiếp trong mssv (ví dụ: task_id='1016')
    # task 5: sử dụng PythonOperator để thực hiện hàm count_data với task_id là 3 chữ số cuối của task4 và số kế tiếp trong mssv (ví dụ: task_id='0169')
    # task 6: sử dụng PythonOperator để thực hiện search bằng vector với task_id là 3 chữ số cuối của task5 và số kế tiếp trong mssv (ví dụ: task_id='1691')
    # task 7: sử dụng BashOperator để in ra "Midterm exam ended" với task_id là 2 số đầu và 2 số cuối của mssv (ví dụ: task_id='1791')

t1 >> t2 >> t3 >> t4 >> t5 >> t6 >> t7