using UnityEngine;
using Unity.Robotics.ROSTCPConnector;
using RosMessageTypes.Std;

public class StringPublisher : MonoBehaviour
{
    ROSConnection ros;
    public string topicName = "unity_chatter";

    public float publishInterval = 2.0f; // 2초 간격
    private float timeSinceLastPublish = 0f;

    void Start()
    {
        ros = ROSConnection.GetOrCreateInstance();
        ros.RegisterPublisher<StringMsg>(topicName);
    }

    void Update()
    {
        timeSinceLastPublish += Time.deltaTime;

        if (timeSinceLastPublish >= publishInterval)
        {
            StringMsg msg = new StringMsg("Hello from Unity!");
            ros.Publish(topicName, msg);
            Debug.Log("Published periodic message to ROS");

            timeSinceLastPublish = 0f;
        }
    }
}