package dispatcher

import (
	"context"
	"fmt"

	"github.com/dacort/claude-os/controller/queue"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/utils/ptr"
)

type Dispatcher struct {
	client    kubernetes.Interface
	namespace string
	image     string
}

func New(client kubernetes.Interface, namespace, image string) *Dispatcher {
	return &Dispatcher{client: client, namespace: namespace, image: image}
}

func (d *Dispatcher) CreateJob(ctx context.Context, task *queue.Task) (*batchv1.Job, error) {
	profile, err := GetProfile(task.Profile)
	if err != nil {
		return nil, fmt.Errorf("get profile: %w", err)
	}

	scratchSize := resource.MustParse(profile.ScratchSize)
	ttl := int32(3600)

	tolerations := make([]corev1.Toleration, len(profile.Tolerations))
	for i, t := range profile.Tolerations {
		tolerations[i] = corev1.Toleration{
			Key:      t.Key,
			Operator: corev1.TolerationOperator(t.Operator),
			Value:    t.Value,
			Effect:   corev1.TaintEffect(t.Effect),
		}
	}

	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("claude-os-%s", task.ID),
			Namespace: d.namespace,
			Labels: map[string]string{
				"app":     "claude-os-worker",
				"task-id": task.ID,
			},
		},
		Spec: batchv1.JobSpec{
			TTLSecondsAfterFinished: &ttl,
			BackoffLimit:            ptr.To(int32(0)),
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						"app":     "claude-os-worker",
						"task-id": task.ID,
					},
				},
				Spec: corev1.PodSpec{
					RestartPolicy:      corev1.RestartPolicyNever,
					ServiceAccountName: "claude-os-controller",
					Tolerations:        tolerations,
					SecurityContext: &corev1.PodSecurityContext{
						RunAsNonRoot:   ptr.To(true),
						RunAsUser:      ptr.To(int64(1000)),
						FSGroup:        ptr.To(int64(1000)),
						SeccompProfile: &corev1.SeccompProfile{Type: corev1.SeccompProfileTypeRuntimeDefault},
					},
					Containers: []corev1.Container{{
						Name:  "worker",
						Image: d.image,
						Env: []corev1.EnvVar{
							{Name: "HOME", Value: "/home/worker"},
							{Name: "TASK_ID", Value: task.ID},
							{Name: "TASK_TITLE", Value: task.Title},
							{Name: "TASK_DESCRIPTION", Value: task.Description},
							{Name: "TARGET_REPO", Value: task.TargetRepo},
							{Name: "TASK_PROFILE", Value: task.Profile},
							{Name: "ANTHROPIC_MODEL", Value: profile.DefaultModel},
						},
						EnvFrom: []corev1.EnvFromSource{
							{SecretRef: &corev1.SecretEnvSource{
								LocalObjectReference: corev1.LocalObjectReference{Name: "claude-os-github"},
							}},
							{SecretRef: &corev1.SecretEnvSource{
								LocalObjectReference: corev1.LocalObjectReference{Name: "claude-os-anthropic"},
							}},
						},
						Resources: corev1.ResourceRequirements{
							Requests: corev1.ResourceList{
								corev1.ResourceCPU:    resource.MustParse(profile.CPURequest),
								corev1.ResourceMemory: resource.MustParse(profile.MemoryRequest),
							},
						},
						SecurityContext: &corev1.SecurityContext{
							RunAsNonRoot:             ptr.To(true),
							ReadOnlyRootFilesystem:   ptr.To(true),
							AllowPrivilegeEscalation: ptr.To(false),
							Capabilities: &corev1.Capabilities{
								Drop: []corev1.Capability{"ALL"},
							},
						},
						VolumeMounts: []corev1.VolumeMount{
							{Name: "workspace", MountPath: "/workspace"},
							{Name: "tmp", MountPath: "/tmp"},
							{Name: "home", MountPath: "/home/worker"},
						},
					}},
					Volumes: []corev1.Volume{
						{
							Name: "workspace",
							VolumeSource: corev1.VolumeSource{
								EmptyDir: &corev1.EmptyDirVolumeSource{SizeLimit: &scratchSize},
							},
						},
						{
							Name: "tmp",
							VolumeSource: corev1.VolumeSource{
								EmptyDir: &corev1.EmptyDirVolumeSource{},
							},
						},
						{
							Name: "home",
							VolumeSource: corev1.VolumeSource{
								EmptyDir: &corev1.EmptyDirVolumeSource{},
							},
						},
					},
				},
			},
		},
	}

	return d.client.BatchV1().Jobs(d.namespace).Create(ctx, job, metav1.CreateOptions{})
}
