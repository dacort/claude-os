package dispatcher

import (
	"context"
	"fmt"
	"regexp"
	"strings"

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

var nonAlphanumDash = regexp.MustCompile(`[^a-z0-9-]`)

// sanitizeName converts a task ID into a valid K8s resource name.
func sanitizeName(id string) string {
	name := strings.ToLower(id)
	name = strings.ReplaceAll(name, "_", "-")
	name = nonAlphanumDash.ReplaceAllString(name, "")
	if len(name) > 50 {
		name = name[:50]
	}
	return strings.Trim(name, "-")
}

// agentSecrets returns the EnvFrom sources, extra env vars, extra volume mounts,
// and extra volumes needed for a given agent type.
func agentSecrets(agent string) ([]corev1.EnvFromSource, []corev1.EnvVar, []corev1.VolumeMount, []corev1.Volume) {
	switch agent {
	case "codex":
		return []corev1.EnvFromSource{
				{SecretRef: &corev1.SecretEnvSource{
					LocalObjectReference: corev1.LocalObjectReference{Name: "claude-os-github"},
				}},
			},
			[]corev1.EnvVar{
				{Name: "CODEX_HOME", Value: "/home/worker/.codex"},
			},
			[]corev1.VolumeMount{
				{Name: "codex-auth", MountPath: "/tmp/codex-auth", ReadOnly: true},
			},
			[]corev1.Volume{
				{
					Name: "codex-auth",
					VolumeSource: corev1.VolumeSource{
						Secret: &corev1.SecretVolumeSource{
							SecretName: "claude-os-codex",
							Optional:   ptr.To(false),
						},
					},
				},
			}
	case "gemini":
		return []corev1.EnvFromSource{
			{SecretRef: &corev1.SecretEnvSource{
				LocalObjectReference: corev1.LocalObjectReference{Name: "claude-os-github"},
			}},
			{SecretRef: &corev1.SecretEnvSource{
				LocalObjectReference: corev1.LocalObjectReference{Name: "claude-os-gemini"},
			}},
		}, nil, nil, nil
	default: // claude
		return []corev1.EnvFromSource{
			{SecretRef: &corev1.SecretEnvSource{
				LocalObjectReference: corev1.LocalObjectReference{Name: "claude-os-github"},
			}},
			{SecretRef: &corev1.SecretEnvSource{
				LocalObjectReference: corev1.LocalObjectReference{Name: "claude-os-oauth"},
				Optional:             ptr.To(true),
			}},
		}, nil, nil, nil
	}
}

func (d *Dispatcher) CreateJob(ctx context.Context, task *queue.Task) (*batchv1.Job, error) {
	profile, err := GetProfile(task.Profile)
	if err != nil {
		return nil, fmt.Errorf("get profile: %w", err)
	}

	agent := task.Agent
	if agent == "" {
		agent = "claude"
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

	envFrom, extraEnv, extraMounts, extraVolumes := agentSecrets(agent)

	env := []corev1.EnvVar{
		{Name: "HOME", Value: "/home/worker"},
		{Name: "TASK_ID", Value: task.ID},
		{Name: "TASK_TITLE", Value: task.Title},
		{Name: "TASK_DESCRIPTION", Value: task.Description},
		{Name: "TARGET_REPO", Value: task.TargetRepo},
		{Name: "TASK_PROFILE", Value: task.Profile},
		{Name: "TASK_AGENT", Value: agent},
		{Name: "ANTHROPIC_MODEL", Value: profile.DefaultModel},
	}
	env = append(env, extraEnv...)

	mounts := []corev1.VolumeMount{
		{Name: "workspace", MountPath: "/workspace"},
		{Name: "tmp", MountPath: "/tmp"},
		{Name: "home", MountPath: "/home/worker"},
	}
	mounts = append(mounts, extraMounts...)

	volumes := []corev1.Volume{
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
	}
	volumes = append(volumes, extraVolumes...)

	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      fmt.Sprintf("claude-os-%s", sanitizeName(task.ID)),
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
						Name:    "worker",
						Image:   d.image,
						Env:     env,
						EnvFrom: envFrom,
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
						VolumeMounts: mounts,
					}},
					Volumes: volumes,
				},
			},
		},
	}

	return d.client.BatchV1().Jobs(d.namespace).Create(ctx, job, metav1.CreateOptions{})
}
